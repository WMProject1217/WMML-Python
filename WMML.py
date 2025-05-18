import os
import json
import platform
import subprocess
from pathlib import Path
from typing import Dict, List, Optional, Union

def launch_minecraft(mc_path: str, version_name: str, player_name: str, options: Dict) -> subprocess.Popen:
    """
    Launches Minecraft with the specified parameters
    
    Args:
        mc_path: Path to .minecraft directory
        version_name: Minecraft version name
        player_name: Player username
        options: Launch options including:
            - java_path: Path to Java executable
            - memory: Memory allocation in MB
            - use_system_memory: Whether to use system memory detection
    """
    try:
        # Normalize path
        mc_path = Path(mc_path)
        if not str(mc_path).endswith(os.sep):
            mc_path = Path(str(mc_path) + os.sep)

        # Read version JSON file
        version_json_path = mc_path / 'versions' / version_name / f'{version_name}.json'
        with open(version_json_path, 'r', encoding='utf-8') as f:
            version_json = json.load(f)

        # Get main class
        main_class = version_json['mainClass']

        # Build libraries path
        libraries = build_libraries_path(mc_path, version_json)

        # Build game arguments
        game_args = build_game_arguments(mc_path, version_name, player_name, version_json)

        # Build Java command
        java_command = build_java_command(mc_path, version_name, main_class, libraries, game_args, options)

        # Execute command
        print('Launching Minecraft with command:', ' '.join(java_command))
        process = subprocess.Popen(
            java_command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            universal_newlines=True
        )

        # Print output in real-time
        def print_output(stream, prefix=''):
            for line in iter(stream.readline, ''):
                print(f'{prefix}{line}', end='')

        import threading
        threading.Thread(target=print_output, args=(process.stdout, '')).start()
        threading.Thread(target=print_output, args=(process.stderr, 'stderr: ')).start()

        return process

    except Exception as error:
        print('Error launching Minecraft:', error)
        raise error

def build_libraries_path(mc_path: Path, version_json: Dict) -> str:
    """
    Builds the libraries classpath
    
    Args:
        mc_path: Path to .minecraft directory
        version_json: Version JSON object
    """
    # Start with the version jar
    result = [str(mc_path / 'versions' / version_json['id'] / f"{version_json['id']}.jar")]

    # Add all libraries
    if 'libraries' in version_json and isinstance(version_json['libraries'], list):
        for lib in version_json['libraries']:
            # Check library rules
            if not check_library_rules(lib):
                continue

            # Get library path
            lib_path = get_library_path(mc_path, lib)
            if lib_path:
                result.append(lib_path)

    return os.pathsep.join(result)

def check_library_rules(lib: Dict) -> bool:
    """
    Checks if a library should be included based on rules
    
    Args:
        lib: Library object
    """
    # If no rules, always include
    if 'rules' not in lib or not lib['rules']:
        return True

    os_name = 'windows'
    os_arch = 'x86_64' if platform.machine().endswith('64') else 'x86'

    should_include = True

    for rule in lib['rules']:
        if rule['action'] == 'allow':
            # If no OS specified, allow
            if 'os' not in rule:
                should_include = True
                continue

            # Check OS condition
            if rule['os']['name'] == os_name:
                # Check arch if specified
                if 'arch' in rule['os']:
                    should_include = (rule['os']['arch'] == os_arch)
                else:
                    should_include = True
            else:
                should_include = False
        elif rule['action'] == 'disallow':
            # If no OS specified, disallow
            if 'os' not in rule:
                should_include = False
                continue

            # Check OS condition
            if rule['os']['name'] == os_name:
                should_include = False

    return should_include

def get_library_path(mc_path: Path, lib: Dict) -> Optional[str]:
    """
    Gets the path to a library file
    
    Args:
        mc_path: Path to .minecraft directory
        lib: Library object
    """
    try:
        parts = lib['name'].split(':')
        group_path = parts[0].replace('.', os.sep)
        artifact_id = parts[1]
        version = parts[2]

        # Base path
        base_path = mc_path / 'libraries' / group_path / artifact_id / version
        base_file = f'{artifact_id}-{version}'

        # Check for natives
        if 'natives' in lib and 'windows' in lib['natives']:
            classifier = lib['natives']['windows'].replace(
                '${arch}', 
                '64' if platform.machine().endswith('64') else '32'
            )
            native_path = base_path / f'{base_file}-{classifier}.jar'

            if native_path.exists():
                return str(native_path)

        # Default to regular jar
        jar_path = base_path / f'{base_file}.jar'
        if jar_path.exists():
            return str(jar_path)

        return None
    except Exception as error:
        print('Error getting library path:', error)
        return None

def build_game_arguments(mc_path: Path, version_name: str, player_name: str, version_json: Dict) -> str:
    """
    Builds the game arguments string
    
    Args:
        mc_path: Path to .minecraft directory
        version_name: Minecraft version name
        player_name: Player username
        version_json: Version JSON object
    """
    assets_path = mc_path / 'assets'
    assets_index = version_json.get('assets', '')

    args = []

    # Handle older versions with minecraftArguments
    if 'minecraftArguments' in version_json:
        args.extend(version_json['minecraftArguments'].split(' '))

    # Handle newer versions with arguments.game
    if 'arguments' in version_json and 'game' in version_json['arguments']:
        for arg in version_json['arguments']['game']:
            if isinstance(arg, str):
                args.append(arg)

    # Join arguments and replace placeholders
    args_str = ' '.join(args)
    
    replacements = {
        '${auth_player_name}': player_name,
        '${version_name}': version_name,
        '${game_directory}': str(mc_path),
        '${assets_root}': str(assets_path),
        '${assets_index_name}': assets_index,
        '${auth_uuid}': '00000000-0000-0000-0000-000000000000',
        '${auth_access_token}': '00000000000000000000000000000000',
        '${user_type}': 'legacy',
        '${version_type}': '"WMML 0.1.26"'
    }

    for placeholder, value in replacements.items():
        args_str = args_str.replace(placeholder, value)

    return args_str.strip()

def build_java_command(
    mc_path: Path, 
    version_name: str, 
    main_class: str, 
    libraries: str, 
    game_args: str, 
    options: Dict
) -> List[str]:
    """
    Builds the complete Java command
    
    Args:
        mc_path: Path to .minecraft directory
        version_name: Minecraft version name
        main_class: Main class to launch
        libraries: Classpath string
        game_args: Game arguments string
        options: Launch options
    """
    java_path = options['java_path']
    memory = options.get('memory', 4096)
    use_system_memory = options.get('use_system_memory', False)

    command = [java_path]

    # Memory settings
    if not use_system_memory and memory:
        command.extend([f'-Xmx{memory}M', f'-Xms{memory}M'])

    # Common JVM arguments
    common_args = [
        '-Dfile.encoding=GB18030',
        '-Dsun.stdout.encoding=GB18030',
        '-Dsun.stderr.encoding=GB18030',
        '-Djava.rmi.server.useCodebaseOnly=true',
        '-Dcom.sun.jndi.rmi.object.trustURLCodebase=false',
        '-Dcom.sun.jndi.cosnaming.object.trustURLCodebase=false',
        '-Dlog4j2.formatMsgNoLookups=true',
        f'-Dlog4j.configurationFile={mc_path / "versions" / version_name / "log4j2.xml"}',
        f'-Dminecraft.client.jar={mc_path / "versions" / version_name / f"{version_name}.jar"}',
        '-XX:+UnlockExperimentalVMOptions',
        '-XX:+UseG1GC',
        '-XX:G1NewSizePercent=20',
        '-XX:G1ReservePercent=20',
        '-XX:MaxGCPauseMillis=50',
        '-XX:G1HeapRegionSize=32m',
        '-XX:-UseAdaptiveSizePolicy',
        '-XX:-OmitStackTraceInFastThrow',
        '-XX:-DontCompileHugeMethods',
        '-Dfml.ignoreInvalidMinecraftCertificates=true',
        '-Dfml.ignorePatchDiscrepancies=true',
        '-XX:HeapDumpPath=MojangTricksIntelDriversForPerformance_javaw.exe_minecraft.exe.heapdump',
        f'-Djava.library.path={mc_path / "versions" / version_name / "natives-windows-x86_64"}',
        f'-Djna.tmpdir={mc_path / "versions" / version_name / "natives-windows-x86_64"}',
        f'-Dorg.lwjgl.system.SharedLibraryExtractPath={mc_path / "versions" / version_name / "natives-windows-x86_64"}',
        f'-Dio.netty.native.workdir={mc_path / "versions" / version_name / "natives-windows-x86_64"}',
        '-Dminecraft.launcher.brand=WMML',
        '-Dminecraft.launcher.version=0.1.26'
    ]

    command.extend(common_args)
    command.extend(['-cp', libraries])
    command.append(main_class)
    command.extend(game_args.split(' '))

    return command

if __name__ == '__main__':
    mc_path = '.minecraft'
    version_name = '1.20.1'
    player_name = 'Player123'

    options = {
        'java_path': 'java',
        'memory': 4096,
        'use_system_memory': False
    }

    try:
        process = launch_minecraft(mc_path, version_name, player_name, options)
        print('Minecraft launched with PID:', process.pid)
    except Exception as e:
        print('Failed to launch Minecraft:', e)