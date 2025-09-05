#!/usr/bin/env python3
import os
import sys
import platform
import shutil
import json
import hashlib
import tempfile
import subprocess
import requests
import time
import requests
from pathlib import Path
from typing import Dict, Optional, Any


from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt, Confirm
from rich.markdown import Markdown
from rich.table import Table
from rich.progress import Progress, TextColumn, BarColumn, DownloadColumn, TransferSpeedColumn, TimeRemainingColumn
from rich.status import Status

console = Console()

# Available Minecraft versions and mod loaders
MINECRAFT_VERSIONS = [version['id']
                      for version in requests.get("https://piston-meta.mojang.com/mc/game/version_manifest_v2.json").json()['versions']
                      if version['type'] == 'release']

# This one is manually added
MOD_LOADERS = {
    "vanilla": {"name": "Vanilla", "description": "Official Minecraft server with no mods"},
    "forge": {"name": "Forge", "description": "Most popular mod loader for many larger mods"},
    "fabric": {"name": "Fabric", "description": "Lightweight mod loader, good for performance mods"},
    "quilt": {"name": "Quilt", "description": "Fork of Fabric with additional features"},
    "neoforge": {"name": "NeoForge", "description": "Modern continuation of the Forge mod loader"}
}

def display_welcome_message():
    """Display a welcome message with instructions."""
    welcome_md = """
    ▀█▀ █▀▀ █▀▀ █▄ █ █▄█ █▀▀ █▀▀ █▀█ █ █ █▀▀ █▀█ █▀▀ █▀▀ █▀█ █ █▀█ ▀█▀
    ░█░░█▀▀░█▀▀░█░▀█░░█░░░▀▄░█▀▀░█▀▄░█░█░█░░░█▀▄░░▀▄░█░░░█▀▄░█░█▀▀░░█░
     ▀  ▀▀▀ ▀▀▀ ▀  ▀  ▀  ▀▀▀ ▀▀▀ ▀ ▀  ▀  ▀▀▀ ▀ ▀ ▀▀▀ ▀▀▀ ▀ ▀ ▀ ▀    ▀
    
    # Minecraft Server Setup

    This script will help you set up a Minecraft server with the following steps:
    
    1. Select Minecraft version
    2. Choose a mod loader
    3. Create server directory
    4. Download server files
    5. Configure initial server settings
    
    Let's get started!
    """
    console.print(Markdown(welcome_md))
    console.print()

def prompt_for_minecraft_version() -> str:
    """Prompt the user to select a Minecraft version."""
    console.print(Panel.fit("Available Minecraft Versions", style="blue"))
    
    table = Table(show_header=True)
    table.add_column("Option", style="dim")
    table.add_column("Version", style="green")
    
    for idx, version in enumerate(MINECRAFT_VERSIONS, 1):
        table.add_row(str(idx), version)
    
    console.print(table)
    
    while True:
        choice = Prompt.ask(
            "Select a Minecraft version [1-{}]".format(len(MINECRAFT_VERSIONS)),
            default="1"
        )
        
        try:
            index = int(choice) - 1
            if 0 <= index < len(MINECRAFT_VERSIONS):
                version = MINECRAFT_VERSIONS[index]
                console.print(f"[green]Selected Minecraft version:[/green] {version}")
                return version
            else:
                console.print("[red]Invalid choice. Please select a number between 1 and {}[/red]".format(len(MINECRAFT_VERSIONS)))
        except ValueError:
            console.print("[red]Please enter a valid number.[/red]")

def prompt_for_mod_loader() -> str:
    """Prompt the user to select a mod loader."""
    console.print(Panel.fit("Available Mod Loaders", style="blue"))
    
    table = Table(show_header=True)
    table.add_column("Option", style="dim")
    table.add_column("Mod Loader", style="green")
    table.add_column("Description", style="yellow")
    
    options = list(MOD_LOADERS.keys())
    for idx, loader_key in enumerate(options, 1):
        loader = MOD_LOADERS[loader_key]
        table.add_row(str(idx), loader["name"], loader["description"])
    
    console.print(table)
    
    while True:
        choice = Prompt.ask(
            "Select a mod loader [1-{}]".format(len(options)),
            default="1"
        )
        
        try:
            index = int(choice) - 1
            if 0 <= index < len(options):
                loader_key = options[index]
                loader_name = MOD_LOADERS[loader_key]["name"]
                console.print(f"[green]Selected mod loader:[/green] {loader_name}")
                return loader_key
            else:
                console.print("[red]Invalid choice. Please select a number between 1 and {}[/red]".format(len(options)))
        except ValueError:
            console.print("[red]Please enter a valid number.[/red]")

def create_server_directory() -> Path:
    """Create and validate the server directory."""
    default_dir = os.path.normpath(os.path.expanduser("~/Desktop/minecraft_server"))
    
    while True:
        server_dir = Prompt.ask(
            "Enter server directory path",
            default=default_dir
        )
        
        server_path = Path(server_dir)
        
        # Check if directory exists
        if server_path.exists():
            if not server_path.is_dir():
                console.print(f"[red]Error: {server_dir} exists but is not a directory[/red]")
                continue
                
            # Directory exists, check if empty
            if any(server_path.iterdir()):
                overwrite = Confirm.ask(
                    f"Directory {server_dir} is not empty. Files may be overwritten. Continue?",
                    default=False
                )
                if not overwrite:
                    continue
        else:
            # Create the directory
            try:
                server_path.mkdir(parents=True, exist_ok=True)
                console.print(f"[green]Created server directory:[/green] {server_dir}")
            except Exception as e:
                console.print(f"[red]Error creating directory: {str(e)}[/red]")
                continue
        
        # Validate directory permissions
        try:
            test_file = server_path / "test_write.tmp"
            with open(test_file, 'w') as f:
                f.write("test")
            test_file.unlink()  # Remove the test file
            break
        except Exception as e:
            console.print(f"[red]Error: Cannot write to directory {server_dir}. Please check permissions.[/red]")
            console.print(f"[red]Details: {str(e)}[/red]")
    
    return server_path

def get_vanilla_download_url(minecraft_version: str) -> Dict[str, str]:
    manifest_url = "https://launchermeta.mojang.com/mc/game/version_manifest.json"
    
    console.print("[bold green]Fetching Minecraft version manifest...[/bold green]")
    response = requests.get(manifest_url)
    response.raise_for_status()
    manifest = response.json()
    
    # Find the specific version
    version_info = None
    for version in manifest["versions"]:
        if version["id"] == minecraft_version:
            version_info = version
            break
    
    if not version_info:
        raise ValueError(f"Minecraft version {minecraft_version} not found in manifest")
    
    # Get version-specific details
    console.print(f"[bold green]Fetching information for Minecraft {minecraft_version}...[/bold green]")
    version_response = requests.get(version_info["url"])
    version_response.raise_for_status()
    version_data = version_response.json()
    
    server_download_info = {
        "url": version_data["downloads"]["server"]["url"],
        "sha1": version_data["downloads"]["server"]["sha1"],
        "size": version_data["downloads"]["server"]["size"],
        "filename": f"minecraft_server.{minecraft_version}.jar"
    }
    
    return server_download_info

def get_forge_download_url(minecraft_version: str) -> Dict[str, str]:
    """Get download URL for Forge server."""
    # Forge has different installer formats for different Minecraft versions
    forge_api_url = "https://files.minecraftforge.net/net/minecraftforge/forge/promotions_slim.json"
    
    console.print("[bold green]Fetching Forge version information...[/bold green]")
    try:
        response = requests.get(forge_api_url)
        response.raise_for_status()
        promotions = response.json()
        
        # Try to find the latest recommended version for this Minecraft version
        forge_version_key = f"{minecraft_version}-recommended"
        if forge_version_key not in promotions["promos"]:
            # If no recommended version, try the latest
            forge_version_key = f"{minecraft_version}-latest"
            if forge_version_key not in promotions["promos"]:
                raise ValueError(f"No Forge version found for Minecraft {minecraft_version}")
        
        forge_version = promotions["promos"][forge_version_key]
        full_forge_version = f"{minecraft_version}-{forge_version}"
        
        # Construct the installer URL
        installer_url = f"https://maven.minecraftforge.net/net/minecraftforge/forge/{full_forge_version}/forge-{full_forge_version}-installer.jar"
        
        # Note: Forge doesn't provide checksums in the API, so we can't verify it
        return {
            "url": installer_url,
            "filename": f"forge-{full_forge_version}-installer.jar",
            "sha1": None,  # Forge doesn't provide checksums in the API
            "size": None,
            "full_version": full_forge_version
        }
    except requests.RequestException as e:
        # Fallback method for older Forge website structure
        console.print(f"[yellow]Warning: Could not fetch Forge info via API. Using fallback method.[/yellow]")
        # Construct a standard URL based on version patterns
        forge_version = "recommended"
        full_forge_version = f"{minecraft_version}-{forge_version}"
        installer_url = f"https://maven.minecraftforge.net/net/minecraftforge/forge/{minecraft_version}-{forge_version}/forge-{minecraft_version}-{forge_version}-installer.jar"
        
        return {
            "url": installer_url,
            "filename": f"forge-{minecraft_version}-{forge_version}-installer.jar",
            "sha1": None,
            "size": None,
            "full_version": full_forge_version
        }

def get_fabric_download_url(minecraft_version: str) -> Dict[str, str]:
    """Get download URL for Fabric server."""
    # Get the latest loader version
    console.print("[bold green]Fetching Fabric loader versions...[/bold green]")
    try:
        loader_url = "https://meta.fabricmc.net/v2/versions/loader"
        response = requests.get(loader_url)
        response.raise_for_status()
        loader_versions = response.json()
        latest_loader = loader_versions[0]["version"]
        
        # First try the direct API URL
        console.print(f"[bold green]Using Fabric loader version {latest_loader}[/bold green]")
        
        # The correct URL pattern for fabric installer
        installer_url = f"https://meta.fabricmc.net/v2/versions/loader/{minecraft_version}/{latest_loader}/server"
        
        # Verify the URL works
        try:
            test_response = requests.head(installer_url)
            if test_response.status_code != 200:
                # If this URL doesn't work, try alternate format
                installer_url = f"https://fabricmc.net/use/server/?intermediary={minecraft_version}&loader={latest_loader}"
                test_response = requests.head(installer_url)
                if test_response.status_code != 200:
                    raise ValueError(f"Could not find valid Fabric server download URL for Minecraft {minecraft_version}")
        except requests.RequestException:
            # If request fails, fall back to generic pattern
            console.print("[yellow]Warning: Could not verify Fabric download URL. Using fallback method.[/yellow]")
            # Use Maven repo as fallback
            installer_url = f"https://maven.fabricmc.net/net/fabricmc/fabric-installer/0.11.2/fabric-installer-0.11.2.jar"
        
        installer_filename = f"fabric-server-mc.{minecraft_version}-loader.{latest_loader}-launcher.jar"
        
        return {
            "url": installer_url,
            "filename": installer_filename,
            "sha1": None,  # Fabric doesn't provide checksums in the API
            "size": None,
            "loader_version": latest_loader,
            "is_installer": True  # Flag to indicate this is an installer rather than direct server jar
        }
    except Exception as e:
        console.print(f"[yellow]Error getting Fabric download information: {str(e)}. Using fallback method.[/yellow]")
        # Use the Fabric installer jar as fallback
        installer_url = "https://maven.fabricmc.net/net/fabricmc/fabric-installer/0.11.2/fabric-installer-0.11.2.jar"
        installer_filename = "fabric-installer-0.11.2.jar"
        
        return {
            "url": installer_url,
            "filename": installer_filename,
            "sha1": None,
            "size": None,
            "loader_version": "0.11.2",
            "is_installer": True
        }

def get_quilt_download_url(minecraft_version: str) -> Dict[str, str]:
    """Get download URL for Quilt server."""
    # Get the latest Quilt loader version
    console.print("[bold green]Fetching Quilt loader versions...[/bold green]")
    loader_url = "https://meta.quiltmc.org/v3/versions/loader"
    response = requests.get(loader_url)
    response.raise_for_status()
    loader_versions = response.json()
    latest_loader = loader_versions[0]["version"]
    
    # Get installer URL
    installer_url = f"https://quiltmc.org/api/v1/download-latest-installer/java-universal"
    installer_filename = f"quilt-server-launch.jar"
    
    return {
        "url": installer_url,
        "filename": installer_filename,
        "sha1": None,  # Quilt doesn't provide checksums in the API
        "size": None,
        "loader_version": latest_loader
    }

def get_neoforge_download_url(minecraft_version: str) -> Dict[str, str]:
    """Get download URL for NeoForge server."""
    # NeoForge is newer and mainly for MC 1.20+
    if minecraft_version.split(".")[1] >= "20":
        raise ValueError(f"NeoForge is only available for Minecraft 1.20+")
    
    # Note: NeoForge versioning and download structure might change
    console.print("[bold green]Fetching NeoForge versions...[/bold green]")
    try:
        # Try the NeoForge API
        api_url = f"https://maven.neoforged.net/api/maven/versions/releases/net/neoforged/neoforge"
        response = requests.get(api_url)
        response.raise_for_status()
        versions = response.json()
        
        # Filter for the requested Minecraft version
        compatible_versions = [v for v in versions if v.startswith(minecraft_version)]
        if not compatible_versions:
            raise ValueError(f"No NeoForge version found for Minecraft {minecraft_version}")
        
        # Get the latest version (they're usually sorted)
        latest_version = max(compatible_versions)
        
        # Construct the installer URL
        installer_url = f"https://maven.neoforged.net/releases/net/neoforged/neoforge/{latest_version}/{latest_version}-installer.jar"
        
        return {
            "url": installer_url,
            "filename": f"neoforge-{latest_version}-installer.jar",
            "sha1": None,
            "size": None,
            "full_version": latest_version
        }
    except (requests.RequestException, ValueError) as e:
        # Fallback for newer versions (this pattern might change)
        console.print(f"[yellow]Warning: Could not fetch NeoForge versions via API. Using fallback method.[/yellow]")
        console.print(f"[yellow]Error details: {str(e)}[/yellow]")
        
        # Fallback to hardcoded versions based on Minecraft version
        if minecraft_version == "1.20.4":
            neoforge_version = "20.4.80-beta"  # Example version, replace with what's current
        else:
            neoforge_version = f"{minecraft_version.replace('1.', '')}.0.0"  # Best guess
        
        installer_url = f"https://maven.neoforged.net/releases/net/neoforged/neoforge/{neoforge_version}/neoforge-{neoforge_version}-installer.jar"
        
        return {
            "url": installer_url,
            "filename": f"neoforge-{neoforge_version}-installer.jar",
            "sha1": None,
            "size": None,
            "full_version": neoforge_version
        }

def download_file(url: str, target_path: Path, file_info: Dict[str, Any]) -> bool:
    """Download a file with progress bar and optional checksum verification."""
    # Ensure directory exists
    target_path.parent.mkdir(parents=True, exist_ok=True)
    
    # Set up progress columns
    progress_columns = [
        TextColumn("[bold blue]{task.description}"),
        BarColumn(),
        DownloadColumn(),
        TransferSpeedColumn(),
        TimeRemainingColumn(),
    ]
    
    try:
        # Download with progress bar
        with Progress(*progress_columns) as progress:
            task_id = progress.add_task(f"Downloading {file_info['filename']}...", total=file_info['size'] if file_info['size'] else None)
            
            # Stream the download to handle large files efficiently
            with requests.get(url, stream=True) as response:
                response.raise_for_status()
                
                # If size wasn't provided, get it from the response headers
                total_size = int(response.headers.get('content-length', 0)) if not file_info['size'] else file_info['size']
                if total_size:
                    progress.update(task_id, total=total_size)
                
                # Use a temporary file during download to avoid corrupted files on failure
                with tempfile.NamedTemporaryFile(delete=False) as temp_file:
                    temp_path = Path(temp_file.name)
                    sha1_hash = hashlib.sha1() if file_info['sha1'] else None
                    
                    # Process the download in chunks
                    chunk_size = 8192  # 8KB chunks
                    downloaded = 0
                    
                    for chunk in response.iter_content(chunk_size=chunk_size):
                        if chunk:
                            temp_file.write(chunk)
                            downloaded += len(chunk)
                            progress.update(task_id, completed=downloaded)
                            
                            # Update hash if we're verifying
                            if sha1_hash:
                                sha1_hash.update(chunk)
                
                # Verify checksum if provided
                if file_info['sha1'] and sha1_hash:
                    calculated_hash = sha1_hash.hexdigest()
                    if calculated_hash != file_info['sha1']:
                        console.print(f"[red]Error: Checksum verification failed for {file_info['filename']}[/red]")
                        console.print(f"[red]Expected: {file_info['sha1']}[/red]")
                        console.print(f"[red]Got: {calculated_hash}[/red]")
                        temp_path.unlink()
                        return False
                
                # Move the temp file to the target location
                shutil.move(str(temp_path), str(target_path))
                return True
                
    except requests.RequestException as e:
        console.print(f"[red]Download failed: {str(e)}[/red]")
        return False
    except Exception as e:
        console.print(f"[red]Error during download: {str(e)}[/red]")
        return False
def generate_server_properties(server_dir: Path) -> Path:
    """Generate default server.properties file."""
    properties_path = server_dir / "server.properties"
    
    # Default server properties
    default_properties = {
        "gamemode": "survival",
        "difficulty": "easy",
        "level-name": "world",
        "motd": "A Minecraft Server",
        "pvp": "true",
        "generate-structures": "true",
        "max-players": "20",
        "online-mode": "true",
        "enable-command-block": "false",
        "server-port": "25565",
        "allow-nether": "true",
        "view-distance": "10",
        "spawn-protection": "16",
        "enable-rcon": "false"
    }
    
    # If file exists, read it first to preserve user settings
    existing_properties = {}
    if properties_path.exists():
        with open(properties_path, 'r') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    key, value = line.split('=', 1)
                    existing_properties[key.strip()] = value.strip()
    
    # Merge defaults with existing properties, prioritizing existing ones
    merged_properties = {**default_properties, **existing_properties}
    
    # Write the properties file
    with open(properties_path, 'w') as f:
        f.write("#Minecraft server properties\n")
        f.write(f"#Generated on {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
        for key, value in sorted(merged_properties.items()):
            f.write(f"{key}={value}\n")
    
    console.print(f"[green]Generated server.properties at:[/green] {properties_path}")
    return properties_path

def accept_eula(server_dir: Path) -> bool:
    """Create or update eula.txt to indicate acceptance."""
    eula_path = server_dir / "eula.txt"
    
    # Display EULA information
    console.print(Panel.fit(
        "By continuing, you are indicating your agreement to Mojang's EULA:\n"
        "https://account.mojang.com/documents/minecraft_eula",
        title="Minecraft EULA",
        border_style="yellow"
    ))
    
    # Ask for EULA acceptance
    accept = Confirm.ask("Do you accept the Minecraft EULA?", default=False)
    if not accept:
        console.print("[yellow]Setup cannot continue without accepting the EULA.[/yellow]")
        return False
    
    # Write the eula.txt file
    with open(eula_path, 'w') as f:
        f.write("#By changing the setting below to TRUE you are indicating your agreement to our EULA (https://account.mojang.com/documents/minecraft_eula).\n")
        f.write(f"#Generated on {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write("eula=true\n")
    
    console.print(f"[green]EULA accepted and saved to:[/green] {eula_path}")
    return True

def install_vanilla_server(download_info: Dict[str, Any], server_dir: Path) -> bool:
    """Install a vanilla Minecraft server."""
    # Just download the server JAR
    jar_path = server_dir / download_info['server_file_info']['filename']
    return download_file(
        download_info['server_file_info']['url'],
        jar_path,
        download_info['server_file_info']
    )

def install_forge_server(download_info: Dict[str, Any], server_dir: Path) -> bool:
    """Install a Forge server using the installer."""
    # Download the installer
    installer_path = server_dir / download_info['server_file_info']['filename']
    if not download_file(
        download_info['server_file_info']['url'],
        installer_path,
        download_info['server_file_info']
    ):
        return False
    
    console.print("[blue]Running Forge installer. This may take a few minutes...[/blue]")
    try:
        # Run the installer with --installServer flag
        console.print("[bold green]Installing Forge server...[/bold green]")
        result = subprocess.run(
            [java_exe, "-jar", str(installer_path), "--installServer"],
            cwd=str(server_dir),
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        
        console.print("[green]Forge server installed successfully![/green]")
        
        # Try to find the run script or main JAR file
        run_files = list(server_dir.glob("run.*")) + list(server_dir.glob("*.sh")) + list(server_dir.glob("forge-*-universal.jar"))
        if run_files:
            download_info['main_jar'] = str(run_files[0].relative_to(server_dir))
            console.print(f"[green]Main server file identified:[/green] {download_info['main_jar']}")
        
        return True
        
    except subprocess.CalledProcessError as e:
        console.print(f"[red]Error running Forge installer:[/red]")
        console.print(f"[red]Exit code: {e.returncode}[/red]")
        console.print(f"[red]Output: {e.stdout}[/red]")
        console.print(f"[red]Error: {e.stderr}[/red]")
        return False
    except Exception as e:
        console.print(f"[red]Error installing Forge server: {str(e)}[/red]")
        return False

def install_fabric_server(download_info: Dict[str, Any], server_dir: Path) -> bool:
    """Install a Fabric server."""
    # Download the server jar or installer
    server_file_info = download_info['server_file_info']
    jar_path = server_dir / server_file_info['filename']
    
    # Download the file
    if not download_file(
        server_file_info['url'],
        jar_path,
        server_file_info
    ):
        return False
    
    # If this is a direct server jar, we're done
    if not server_file_info.get('is_installer', False):
        return True
    
    # If this is an installer, we need to run it
    java_exe = download_info['java_executable']
    if not java_exe:
        console.print("[red]Java is required to install Fabric. Please install Java and try again.[/red]")
        return False
    
    console.print("[blue]Running Fabric installer. This may take a few minutes...[/blue]")
    try:
        # Create a temp directory for the installation
        console.print("[bold green]Installing Fabric server...[/bold green]")
        
        # Run the installer with the server command
        result = subprocess.run(
            [
                java_exe, 
                "-jar", 
                str(jar_path), 
                "server", 
                "-mcversion", download_info['minecraft_version'],
                "-loader", server_file_info.get('loader_version', "0.14.21"),
                "-dir", str(server_dir)
            ],
            cwd=str(server_dir),
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        
        console.print("[green]Fabric server installed successfully![/green]")
        
        # Try to find the main server jar
        server_jars = list(server_dir.glob("fabric-server-launch.jar")) + \
                     list(server_dir.glob("*-fabric-server.jar")) + \
                     list(server_dir.glob("server.jar"))
        
        if server_jars:
            download_info['main_jar'] = str(server_jars[0].relative_to(server_dir))
            console.print(f"[green]Main server file identified:[/green] {download_info['main_jar']}")
            return True
        else:
            console.print("[yellow]Fabric server installed but could not find main JAR. You may need to set it manually.[/yellow]")
            # Just use the installer as a fallback
            download_info['main_jar'] = server_file_info['filename']
            return True
            
    except subprocess.CalledProcessError as e:
        console.print(f"[red]Error running Fabric installer:[/red]")
        console.print(f"[red]Exit code: {e.returncode}[/red]")
        console.print(f"[red]Output: {e.stdout}[/red]")
        console.print(f"[red]Error: {e.stderr}[/red]")
        return False
    except Exception as e:
        console.print(f"[red]Error installing Fabric server: {str(e)}[/red]")
        return False

def install_quilt_server(download_info: Dict[str, Any], server_dir: Path) -> bool:
    """Install a Quilt server."""
    # Similar to Fabric, just download the server JAR
    jar_path = server_dir / download_info['server_file_info']['filename']
    return download_file(
        download_info['server_file_info']['url'],
        jar_path,
        download_info['server_file_info']
    )

def install_neoforge_server(download_info: Dict[str, Any], server_dir: Path) -> bool:
    """Install a NeoForge server using the installer."""
    # Similar to Forge but with NeoForge specifics
    installer_path = server_dir / download_info['server_file_info']['filename']
    if not download_file(
        download_info['server_file_info']['url'],
        installer_path,
        download_info['server_file_info']
    ):
        return False
    
    # Run the installer to set up the server
    java_exe = download_info['java_executable']
    if not java_exe:
        console.print("[red]Java is required to install NeoForge. Please install Java and try again.[/red]")
        return False
    
    console.print("[blue]Running NeoForge installer. This may take a few minutes...[/blue]")
    try:
        # Run the installer with appropriate flags
        console.print("[bold green]Installing NeoForge server...[/bold green]")
        result = subprocess.run(
            [java_exe, "-jar", str(installer_path), "--installServer"],
            cwd=str(server_dir),
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        
        console.print("[green]NeoForge server installed successfully![/green]")
        
        # Try to find the main server file
        run_files = list(server_dir.glob("run.*")) + list(server_dir.glob("*.sh")) + list(server_dir.glob("neoforge-*-server.jar"))
        if run_files:
            download_info['main_jar'] = str(run_files[0].relative_to(server_dir))
            console.print(f"[green]Main server file identified:[/green] {download_info['main_jar']}")
        
        return True
        
    except subprocess.CalledProcessError as e:
        console.print(f"[red]Error running NeoForge installer:[/red]")
        console.print(f"[red]Exit code: {e.returncode}[/red]")
        console.print(f"[red]Output: {e.stdout}[/red]")
        console.print(f"[red]Error: {e.stderr}[/red]")
        return False
    except Exception as e:
        console.print(f"[red]Error installing NeoForge server: {str(e)}[/red]")
        return False

def download_and_install_server(download_info: Dict[str, Any]) -> bool:
    """Download and install the Minecraft server based on the selected mod loader."""
    mod_loader = download_info["mod_loader"]
    server_dir = download_info["server_dir"]
    
    console.print(Panel.fit(f"Downloading and Installing {MOD_LOADERS[mod_loader]['name']} Server", style="blue"))
    
    # Install based on mod loader type
    try:
        if mod_loader == "vanilla":
            success = install_vanilla_server(download_info, server_dir)
        elif mod_loader == "forge":
            success = install_forge_server(download_info, server_dir)
        elif mod_loader == "fabric":
            success = install_fabric_server(download_info, server_dir)
        elif mod_loader == "quilt":
            success = install_quilt_server(download_info, server_dir)
        elif mod_loader == "neoforge":
            success = install_neoforge_server(download_info, server_dir)
        else:
            console.print(f"[red]Unknown mod loader: {mod_loader}[/red]")
            return False
        
        if not success:
            console.print(f"[red]Failed to install {MOD_LOADERS[mod_loader]['name']} server.[/red]")
            return False
        
        # Generate server.properties and accept EULA
        generate_server_properties(server_dir)
        if not accept_eula(server_dir):
            console.print("[yellow]EULA not accepted. Server will not start without accepting the EULA.[/yellow]")
            return False
        
        return True
        
    except Exception as e:
        console.print(f"[red]Error during server installation: {str(e)}[/red]")
        import traceback
        console.print(traceback.format_exc())
        return False

def test_server_startup(download_info: Dict[str, Any]) -> bool:
    """Test that the server can start up properly."""
    java_exe = download_info.get("java_executable")
    if not java_exe:
        console.print("[red]Java is required to test the server. Please install Java and try again.[/red]")
        return False
    
    server_dir = download_info["server_dir"]
    main_jar = download_info.get("main_jar")
    
    if not main_jar:
        # Try to find the main JAR file
        jar_files = list(server_dir.glob("*.jar"))
        if not jar_files:
            console.print("[red]No JAR files found in the server directory.[/red]")
            return False
        main_jar = str(jar_files[0].relative_to(server_dir))
        download_info["main_jar"] = main_jar
    
    console.print(f"[blue]Testing server startup with {main_jar}...[/blue]")
    
    try:
        # Run the server with nogui option for a brief period to test startup
        with Status("[bold green]Starting server for testing (will be stopped after a few seconds)...[/bold green]"):
            process = subprocess.Popen(
                [java_exe, "-Xmx1G", "-jar", main_jar, "nogui"],
                cwd=str(server_dir),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )
            
            # Wait for a short time to see if server starts
            time.sleep(10)
            
            # Check if the process is still running and stop it
            if process.poll() is None:
                # Server started successfully, now stop it
                console.print("[green]Server started successfully![/green]")
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                return True
            else:
                # Server failed to start
                stdout, stderr = process.communicate()
                console.print("[red]Server failed to start.[/red]")
                console.print(f"[red]Exit code: {process.returncode}[/red]")
                console.print(f"[red]Output: {stdout}[/red]")
                console.print(f"[red]Error: {stderr}[/red]")
                return False
                
    except Exception as e:
        console.print(f"[red]Error testing server startup: {str(e)}[/red]")
        return False

def save_server_info(download_info: Dict[str, Any]) -> Path:
    """Save server information to a JSON file for later use."""
    server_dir = download_info["server_dir"]
    info_file = server_dir / "server_info.json"
    
    # Convert Path objects to strings for JSON serialization
    serializable_info = {k: (str(v) if isinstance(v, Path) else v) for k, v in download_info.items()}
    
    with open(info_file, 'w') as f:
        json.dump(serializable_info, f, indent=2)
    
    console.print(f"[green]Server information saved to:[/green] {info_file}")
    return info_file

def create_startup_scripts(download_info: Dict[str, Any]) -> None:
    """Create startup scripts for the server."""
    server_dir = download_info["server_dir"]
    java_executable = download_info.get("java_executable", "java")
    main_jar = download_info.get("main_jar", "server.jar")
    
    # Determine memory settings - default to 2GB
    memory = "2G"
    
    # Create batch file for Windows
    batch_path = server_dir / "start_server.bat"
    with open(batch_path, 'w') as f:
        f.write(f'@echo off\r\n')
        f.write(f'echo Starting Minecraft Server...\r\n')
        f.write(f'"{java_executable}" -Xmx{memory} -Xms{memory} -jar {main_jar} nogui\r\n')
        f.write(f'echo Server stopped. Press any key to exit.\r\n')
        f.write(f'pause > nul\r\n')
    
    console.print(f"[green]Created Windows startup script:[/green] {batch_path}")
    
    # Create shell script for Unix-like systems
    sh_path = server_dir / "start_server.sh"
    with open(sh_path, 'w') as f:
        f.write(f'#!/bin/sh\n')
        f.write(f'echo "Starting Minecraft Server..."\n')
        f.write(f'{java_executable} -Xmx{memory} -Xms{memory} -jar {main_jar} nogui\n')
        f.write(f'echo "Server stopped."\n')
    
    # Make the shell script executable on Unix-like systems
    if platform.system() != "Windows":
        try:
            sh_path.chmod(sh_path.stat().st_mode | 0o111)  # Add executable bit
        except Exception as e:
            console.print(f"[yellow]Warning: Could not make shell script executable: {str(e)}[/yellow]")
    
    console.print(f"[green]Created Unix startup script:[/green] {sh_path}")
    
    return batch_path, sh_path

def find_java_executable() -> Optional[str]:
    """Find the Java executable on the system.
    
    Searches for Java in common installation locations.
    Prefers newer Java versions for Minecraft compatibility.
    
    Returns:
        The path to the Java executable or None if not found.
    """
    # First try the PATH environment variable
    java_path = shutil.which("java")
    if java_path:
        return java_path
    
    # Common Java installation directories by OS
    if platform.system() == "Windows":
        # Windows: Check Program Files directories and registry
        search_paths = [
            os.path.join(os.environ.get("PROGRAMFILES", "C:\\Program Files"), "Java"),
            os.path.join(os.environ.get("PROGRAMFILES(X86)", "C:\\Program Files (x86)"), "Java"),
            os.path.join(os.environ.get("LOCALAPPDATA", ""), "Programs\\AdoptOpenJDK"),
            os.path.join(os.environ.get("LOCALAPPDATA", ""), "Programs\\Eclipse Adoptium")
        ]
        
        java_dirs = []
        for search_path in search_paths:
            if os.path.exists(search_path):
                # Look for jdk/jre directories
                for item in os.listdir(search_path):
                    item_path = os.path.join(search_path, item)
                    if os.path.isdir(item_path) and ("jdk" in item.lower() or "jre" in item.lower()):
                        bin_path = os.path.join(item_path, "bin")
                        if os.path.exists(bin_path):
                            java_exe = os.path.join(bin_path, "java.exe")
                            if os.path.exists(java_exe):
                                java_dirs.append((java_exe, item))
        
        # Try to find via registry as a backup
        try:
            import winreg
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\JavaSoft\Java Runtime Environment") as key:
                current_version, _ = winreg.QueryValueEx(key, "CurrentVersion")
                with winreg.OpenKey(key, current_version) as version_key:
                    java_home, _ = winreg.QueryValueEx(version_key, "JavaHome")
                    java_exe = os.path.join(java_home, "bin", "java.exe")
                    if os.path.exists(java_exe):
                        java_dirs.append((java_exe, f"Java {current_version} (Registry)"))
        except (ImportError, OSError, FileNotFoundError):
            # Registry check failed, continue with other methods
            pass
            
    else:
        # Unix-like systems (Linux, macOS)
        search_paths = [
            "/usr/lib/jvm",  # Linux
            "/usr/java",     # Linux
            "/usr/local/java", # Linux/macOS
            "/opt/java",     # Linux
            "/Library/Java/JavaVirtualMachines"  # macOS
        ]
        
        # macOS-specific paths
        if platform.system() == "Darwin":
            search_paths.append("/System/Library/Java/JavaVirtualMachines")
        
        java_dirs = []
        for search_path in search_paths:
            if os.path.exists(search_path):
                for item in os.listdir(search_path):
                    item_path = os.path.join(search_path, item)
                    if os.path.isdir(item_path):
                        # Check for bin directory directly
                        bin_path = os.path.join(item_path, "bin")
                        if os.path.exists(bin_path):
                            java_exe = os.path.join(bin_path, "java")
                            if os.path.exists(java_exe):
                                java_dirs.append((java_exe, item))
                        
                        # macOS-style: JDK/Contents/Home/bin
                        home_path = os.path.join(item_path, "Contents", "Home") if platform.system() == "Darwin" else None
                        if home_path and os.path.exists(home_path):
                            bin_path = os.path.join(home_path, "bin")
                            if os.path.exists(bin_path):
                                java_exe = os.path.join(bin_path, "java")
                                if os.path.exists(java_exe):
                                    java_dirs.append((java_exe, item))
    
    # If no Java found in common locations, try one more fallback for Unix-like systems
    if not java_dirs and platform.system() != "Windows":
        try:
            # Try using the 'which' command
            process = subprocess.run(['which', 'java'], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            if process.returncode == 0:
                java_path = process.stdout.strip()
                if java_path:
                    return java_path
        except Exception:
            pass
    
    # Sort based on Java version (prefer Java 17+ for modern Minecraft)
    if java_dirs:
        # Check which Java versions we have
        version_info = []
        for java_exe, label in java_dirs:
            try:
                version_output = subprocess.run(
                    [java_exe, "-version"], 
                    stdout=subprocess.PIPE, 
                    stderr=subprocess.PIPE, 
                    text=True, 
                    check=True
                ).stderr
                
                # Identify major version
                major_version = 8  # Default to Java 8
                if "version" in version_output:
                    version_str = version_output.split('"')[1] if '"' in version_output else version_output
                    
                    # Handle different version formats
                    if version_str.startswith("1."):
                        # Old format: 1.8.0_292
                        major_version = int(version_str.split(".")[1])
                    else:
                        # New format: 11.0.11, 17.0.2
                        major_version = int(version_str.split(".")[0])
                
                version_info.append((java_exe, major_version, label))
            except Exception:
                # Couldn't determine version, assume it's Java 8
                version_info.append((java_exe, 8, label))
        
        # Sort by version (descending) - prefer newer versions
        version_info.sort(key=lambda x: x[1], reverse=True)
        
        # Get the best Java for Minecraft
        best_java = version_info[0][0]
        best_version = version_info[0][1]
        best_label = version_info[0][2]
        
        # Log what we found
        console.print(f"[green]Found Java {best_version} at: {best_java}[/green]")
        return best_java
    
    # No suitable Java found
    console.print("[yellow]Warning: Java not found in PATH or common installation directories.[/yellow]")
    console.print("[yellow]You'll need to install Java to run a Minecraft server.[/yellow]")
    return None

def get_java_version(java_executable: str) -> str:
    """Get the Java version from the executable."""
    try:
        result = subprocess.run(
            [java_executable, "-version"],
            capture_output=True,
            text=True,
            check=True
        )
        # Java outputs version to stderr
        version_output = result.stderr
        # Parse the version string
        if "version" in version_output:
            version_line = version_output.splitlines()[0]
            return version_line
        return "Unknown"
    except Exception:
        return "Error detecting version"

def prepare_for_download(minecraft_version: str, mod_loader: str, server_dir: Path) -> Dict[str, Any]:
    """Prepare configuration for downloading server files based on Minecraft version and mod loader."""
    console.print("[bold blue]Preparing for server download...[/bold blue]")
    
    # Get Java executable
    java_executable = find_java_executable()
    if not java_executable:
        console.print("[red]Java is required to run a Minecraft server. Please install Java before continuing.[/red]")
        if Confirm.ask("Continue anyway?", default=False):
            console.print("[yellow]Continuing without Java. You will need to install it before running the server.[/yellow]")
        else:
            raise ValueError("Java is required for Minecraft server installation")
    
    # Get system information
    system_info = {
        "os": platform.system(),
        "architecture": platform.architecture()[0],
        "processor": platform.processor()
    }
    
    # Check Java version if Java is available
    if java_executable:
        java_version_str = get_java_version(java_executable)
        system_info["java_version"] = java_version_str
        
        # Add a warning for older Java versions depending on Minecraft version
        if minecraft_version.split(".")[1] >= "17":
            console.print("[yellow]Warning: You need to have java 8 installed[/yellow]]")
        if minecraft_version.split(".")[1] >= "20":
            console.print("[yellow]Warning: Minecraft 1.18+ works best with Java 17 or newer.[/yellow]")
    
    # Get download information based on mod loader
    try:
        console.print(f"[bold green]Getting download information for {MOD_LOADERS[mod_loader]['name']}...[/bold green]")
        server_file_info = None
        
        if mod_loader == "vanilla":
            server_file_info = get_vanilla_download_url(minecraft_version)
        elif mod_loader == "forge":
            server_file_info = get_forge_download_url(minecraft_version)
        elif mod_loader == "fabric":
            server_file_info = get_fabric_download_url(minecraft_version)
        elif mod_loader == "quilt":
            server_file_info = get_quilt_download_url(minecraft_version)
        elif mod_loader == "neoforge":
            server_file_info = get_neoforge_download_url(minecraft_version)
        else:
            raise ValueError(f"Unknown mod loader: {mod_loader}")
        
        if not server_file_info:
            raise ValueError(f"Failed to get download information for {minecraft_version} with {mod_loader}")
    except Exception as e:
        console.print(f"[red]Error getting download information: {str(e)}[/red]")
        raise
    
    # Create the complete download info dictionary
    download_info = {
        "minecraft_version": minecraft_version,
        "mod_loader": mod_loader,
        "server_dir": server_dir,
        "java_executable": java_executable,
        "system_info": system_info,
        "server_file_info": server_file_info,
        "main_jar": server_file_info["filename"],  # Will be updated for mod loaders after installation
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")
    }
    
    # Display download configuration
    console.print(Panel.fit("Server Download Configuration", style="green"))
    
    table = Table(show_header=True)
    table.add_column("Setting", style="blue")
    table.add_column("Value", style="green")
    
    table.add_row("Minecraft Version", minecraft_version)
    table.add_row("Mod Loader", MOD_LOADERS[mod_loader]["name"])
    table.add_row("Server Directory", str(server_dir))
    table.add_row("Java Executable", download_info["java_executable"] or "Not found")
    table.add_row("Operating System", download_info["system_info"]["os"])
    if "java_version" in system_info:
        table.add_row("Java Version", system_info["java_version"])
    if "full_version" in server_file_info:
        table.add_row(f"{MOD_LOADERS[mod_loader]['name']} Version", server_file_info["full_version"])
    if "loader_version" in server_file_info:
        table.add_row(f"{MOD_LOADERS[mod_loader]['name']} Loader", server_file_info["loader_version"])
    table.add_row("Server File", server_file_info["filename"])
    
    console.print(table)
    return download_info

def main():
    """Main function to run the setup process."""
    try:
        # Step 1: Display welcome message
        display_welcome_message()
        
        # Step 2: Prompt for Minecraft version
        minecraft_version = prompt_for_minecraft_version()
        
        # Step 3: Prompt for mod loader
        mod_loader = prompt_for_mod_loader()
        
        # Step 4: Create server directory
        server_dir = create_server_directory()
        
        # Step 5: Prepare for download
        download_info = prepare_for_download(minecraft_version, mod_loader, server_dir)
        
        # Step 6: Download and install server
        if download_and_install_server(download_info):
            console.print(Panel.fit("Server installed successfully!", style="green"))
            
            # Step 7: Test server startup
            console.print("\n[blue]Testing server startup...[/blue]")
            if test_server_startup(download_info):
                console.print("[green]Server startup test passed![/green]")
            else:
                console.print("[yellow]Server startup test failed. You may need to troubleshoot the installation.[/yellow]")
                if not Confirm.ask("Continue with setup?", default=True):
                    return
            
            # Step 8: Create startup scripts
            console.print("\n[blue]Creating startup scripts...[/blue]")
            create_startup_scripts(download_info)
            
            # Step 9: Save server information
            info_file = save_server_info(download_info)
            
            # Final message
            console.print("\n" + Panel.fit(
                f"[bold green]Server setup complete![/bold green]\n\n"
                f"Your Minecraft {download_info['minecraft_version']} server with {MOD_LOADERS[download_info['mod_loader']]['name']} "
                f"has been set up in:\n[bold]{server_dir}[/bold]\n\n"
                f"To start the server, run the start_server script in the server directory.\n"
                f"Server information has been saved to: {info_file.name}",
                title="Setup Complete",
                border_style="green"
            ))
        else:
            console.print(Panel.fit("Server installation failed. See error messages above.", style="red"))
    
    except KeyboardInterrupt:
        console.print("\n[yellow]Setup canceled by user.[/yellow]")
        sys.exit(1)
    except Exception as e:
        console.print(f"[red]An unexpected error occurred: {str(e)}[/red]")
        import traceback
        console.print(traceback.format_exc())
        sys.exit(1)

if __name__ == "__main__":
    main()
