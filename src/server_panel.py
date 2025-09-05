#!/usr/bin/env python3
import os
import sys
import json
import time
import platform
import requests
import subprocess
import shutil
import socket
import psutil
import threading
import re
from datetime import datetime
from pathlib import Path
from typing import Dict, Any


from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt, Confirm
from rich.table import Table
from rich.box import ROUNDED
from rich.syntax import Syntax
from rich.status import Status

# Import Minecraft versions from the setup script
MINECRAFT_VERSIONS = [x['id'] for x in requests.get("https://piston-meta.mojang.com/mc/game/version_manifest_v2.json").json()['versions']]

# Initialize console
console = Console()

# Define constants
CONFIG_FILES = {
    "server.properties": "Server properties",
    "eula.txt": "End User License Agreement",
    "ops.json": "Server operators",
    "banned-players.json": "Banned players",
    "banned-ips.json": "Banned IPs",
    "whitelist.json": "Whitelisted players"
}

class MinecraftServerManager:
    """Manages a Minecraft server installation."""
    
    def __init__(self):
        self.server_dir = None
        self.server_info = None
        self.server_process = None
        self.java_executable = None
        self.main_jar = None
        self.minecraft_version = None
        self.mod_loader = None
        self.is_running = False
        self.log_thread = None
        self.stop_log_thread = False
        self.log_buffer = []
        self.max_log_lines = 100
        self.console_input_mode = False
        self.last_status_check = 0
        self.local_ip = self._get_local_ip()
        self.server_port = 25565  # Default Minecraft port
        self.tunnel_info = {}
        self.resource_usage = {
            "cpu": 0.0,
            "memory": 0,
            "memory_percent": 0.0,
            "uptime": 0,
        }
        
    def _get_local_ip(self) -> str:
        """Get the local IP address of the machine."""
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            local_ip = s.getsockname()[0]
            s.close()
            return local_ip
        except:
            return "127.0.0.1"
    def load_server_info(self) -> bool:
        """Load server information from server_info.json."""
        # Search for server_info.json in multiple potential locations
        potential_locations = [
            Path("server_info.json"),                                 # Current directory
            Path("minecraft_server/server_info.json"),                # minecraft_server subdirectory
            Path.home() / "minecraft_server" / "server_info.json",    # User's home/minecraft_server
            Path("./minecraft_server/server_info.json")               # Relative minecraft_server path
        ]
        
        # Try each location
        server_info_path = None
        for location in potential_locations:
            if location.exists():
                server_info_path = location
                self.server_dir = location.parent
                console.print(f"[green]Found server_info.json at:[/green] {location}")
                break
        
        # If not found in standard locations, ask for server directory
        if not server_info_path:
            console.print("[yellow]server_info.json not found in standard locations.[/yellow]")
            console.print("[yellow]Please specify your Minecraft server directory.[/yellow]")
            server_dir = Prompt.ask(
                "Enter the path to your Minecraft server directory",
                default=str(Path.home() / "minecraft_server")
            )
            
            # Handle both relative and absolute paths
            server_path = Path(server_dir)
            if not server_path.is_absolute():
                server_path = Path.cwd() / server_path
                
            server_info_path = server_path / "server_info.json"
            
            # Check if the specified path exists
            if not server_path.exists():
                console.print(f"[red]Directory {server_dir} does not exist.[/red]")
                return False
                
            # Check if server_info.json exists in the specified path
            if not server_info_path.exists():
                console.print(f"[red]server_info.json not found at {server_info_path}[/red]")
                console.print(f"[red]server_info.json not found at {server_info_path}[/red]")
                
                # Last attempt - look for server.jar files
                if Path(server_dir).exists():
                    jar_files = list(Path(server_dir).glob("*.jar"))
                    if jar_files:
                        console.print(f"[yellow]Found {len(jar_files)} JAR files in directory, but no server_info.json.[/yellow]")
                        self.server_dir = Path(server_dir)
                        self.main_jar = str(jar_files[0].name)
                        self.java_executable = shutil.which("java")
                        self.minecraft_version = "unknown"
                        self.mod_loader = "unknown"
                        self.server_port = 25565
                        
                        # Try to get the version from file name
                        jar_name = jar_files[0].name.lower()
                        if "forge" in jar_name:
                            self.mod_loader = "forge"
                        elif "fabric" in jar_name:
                            self.mod_loader = "fabric"
                        elif "quilt" in jar_name:
                            self.mod_loader = "quilt"
                        elif "neoforge" in jar_name:
                            self.mod_loader = "neoforge"
                        else:
                            self.mod_loader = "vanilla"
                            
                        if Confirm.ask("Continue with detected server?", default=True):
                            # Create a minimal server_info.json
                            self.server_info = {
                                "server_dir": str(self.server_dir),
                                "main_jar": self.main_jar,
                                "java_executable": self.java_executable,
                                "minecraft_version": self.minecraft_version,
                                "mod_loader": self.mod_loader,
                                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                            }
                            self._save_server_info()
                            return True
                return False
        
        # Read server info
        try:
            # Store the server directory path (parent of server_info.json) for consistency
            if server_info_path:
                self.server_dir = server_info_path.parent
                
                with open(server_info_path, 'r') as f:
                    self.server_info = json.load(f)
                
                # Extract relevant information
                # Note: We keep the server_dir from the file but validate it exists
                server_dir_from_file = Path(self.server_info.get("server_dir", str(self.server_dir)))
                
                # If the directory in the JSON doesn't exist but our detected one does, use the detected one
                if not server_dir_from_file.exists() and self.server_dir.exists():
                    console.print(f"[yellow]Warning: Server directory in config ({server_dir_from_file}) doesn't exist.[/yellow]")
                    console.print(f"[yellow]Using detected directory: {self.server_dir}[/yellow]")
                    self.server_info["server_dir"] = str(self.server_dir)
                else:
                    self.server_dir = server_dir_from_file
                
                self.main_jar = self.server_info.get("main_jar")
                self.java_executable = self.server_info.get("java_executable")
                self.minecraft_version = self.server_info.get("minecraft_version", "unknown")
                self.mod_loader = self.server_info.get("mod_loader", "vanilla")
            
            # Check if we have a valid JAR file
            if not self.main_jar or not (self.server_dir / self.main_jar).exists():
                # Try to find the main JAR
                jar_files = list(self.server_dir.glob("*.jar"))
                if jar_files:
                    self.main_jar = str(jar_files[0].relative_to(self.server_dir))
                    self.server_info["main_jar"] = self.main_jar
                    self._save_server_info()
                else:
                    console.print("[red]No server JAR files found in the server directory![/red]")
                    return False
            
            # Check if we have Java
            if not self.java_executable or not shutil.which(self.java_executable):
                self.java_executable = shutil.which("java")
                if self.java_executable:
                    self.server_info["java_executable"] = self.java_executable
                    self._save_server_info()
                else:
                    console.print("[red]Java not found! Please install Java before running the server.[/red]")
                    return False
            
            # Read server port from server.properties
            properties_path = self.server_dir / "server.properties"
            if properties_path.exists():
                with open(properties_path, 'r') as f:
                    for line in f:
                        if line.startswith("server-port="):
                            try:
                                self.server_port = int(line.split("=")[1].strip())
                                break
                            except ValueError:
                                pass
            
            # Validate critical fields
            if not self.main_jar:
                # Try to find the main JAR in the server directory
                jar_files = list(self.server_dir.glob("*.jar"))
                if jar_files:
                    jar_name = jar_files[0].name
                    console.print(f"[yellow]No main JAR specified in config. Using detected JAR: {jar_name}[/yellow]")
                    self.main_jar = jar_name
                    self.server_info["main_jar"] = jar_name
                    self._save_server_info()
                else:
                    console.print("[yellow]Warning: No server JAR found in the server directory.[/yellow]")
            
            # Look for Java if not specified or not found
            if not self.java_executable or not shutil.which(self.java_executable):
                # Try to find Java
                java_path = shutil.which("java")
                if java_path:
                    console.print(f"[yellow]Using Java from PATH: {java_path}[/yellow]")
                    self.java_executable = java_path
                    self.server_info["java_executable"] = java_path
                    self._save_server_info()
            
            console.print(f"[green]Loaded server information for Minecraft {self.minecraft_version} with {self.mod_loader}[/green]")
            return True
            
        except Exception as e:
            console.print(f"[red]Error loading server information: {str(e)}[/red]")
            return False
    
    def _save_server_info(self) -> None:
        """Save current server info back to server_info.json."""
        try:
            info_file = self.server_dir / "server_info.json"
            with open(info_file, 'w') as f:
                json.dump(self.server_info, f, indent=2)
        except Exception as e:
            console.print(f"[yellow]Warning: Could not save server info: {str(e)}[/yellow]")
    
    def start_server(self) -> bool:
        """Start the Minecraft server."""
        if self.is_running:
            console.print("[yellow]Server is already running.[/yellow]")
            return True
        
        if not self.server_dir or not self.main_jar or not self.java_executable:
            console.print("[red]Server information is incomplete. Cannot start server.[/red]")
            return False
        
        # Check if EULA is accepted
        eula_path = self.server_dir / "eula.txt"
        if eula_path.exists():
            with open(eula_path, 'r') as f:
                eula_content = f.read()
                if "eula=false" in eula_content.lower():
                    console.print("[red]Minecraft EULA not accepted. Server cannot start.[/red]")
                    if Confirm.ask("Accept EULA now?", default=True):
                        with open(eula_path, 'w') as f:
                            f.write("#By changing the setting below to TRUE you are indicating your agreement to our EULA (https://account.mojang.com/documents/minecraft_eula).\n")
                            f.write(f"#Generated on {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
                            f.write("eula=true\n")
                        console.print("[green]EULA accepted.[/green]")
                    else:
                        return False
        
        # Start the server
        try:
            main_jar_path = self.server_dir / self.main_jar
            
            # Memory settings - default to 2GB
            memory = "2G"
            
            with Status("[bold green]Starting Minecraft server...[/bold green]"):
                server_command = [
                    self.java_executable,
                    f"-Xmx{memory}",
                    f"-Xms{memory}",
                    "-jar",
                    str(main_jar_path),
                    "nogui"
                ]
                
                self.server_process = subprocess.Popen(
                    server_command,
                    cwd=str(self.server_dir),
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    stdin=subprocess.PIPE,
                    text=True,
                    bufsize=1,
                    universal_newlines=True
                )
                
                # Start log reading thread
                self.stop_log_thread = False
                self.log_thread = threading.Thread(target=self._read_server_output)
                self.log_thread.daemon = True
                self.log_thread.start()
                
                # Wait until server is ready or failed
                ready = False
                fail = False
                start_time = time.time()
                
                # Wait up to 60 seconds for server to start
                while time.time() - start_time < 60:
                    if not self.server_process or self.server_process.poll() is not None:
                        fail = True
                        break
                        
                    # Check logs for success or failure indicators
                    for log in self.log_buffer:
                        if "Done" in log and "For help, type" in log:
                            ready = True
                            break
                        if "FAILED TO BIND TO PORT" in log:
                            fail = True
                            break
                    
                    if ready or fail:
                        break
                        
                    time.sleep(0.5)
                
                if not self.server_process or self.server_process.poll() is not None:
                    console.print("[red]Server failed to start. Check logs for details.[/red]")
                    self.server_process = None
                    return False
                
                # Set server as running
                self.is_running = True
                self._update_resource_usage()
                
                console.print("[green]Minecraft server started successfully![/green]")
                return True
                
        except Exception as e:
            console.print(f"[red]Error starting server: {str(e)}[/red]")
            self.server_process = None
            return False
    
    def stop_server(self) -> bool:
        """Stop the Minecraft server gracefully."""
        if not self.is_running or not self.server_process:
            console.print("[yellow]Server is not running.[/yellow]")
            return True
        
        try:
            with Status("[bold yellow]Stopping Minecraft server...[/bold yellow]"):
                # Send stop command
                self.send_command("stop")
                
                # Wait for process to terminate (up to 30 seconds)
                for _ in range(30):
                    if self.server_process.poll() is not None:
                        break
                    time.sleep(1)
                
                # If still running, forcefully terminate
                if self.server_process.poll() is None:
                    console.print("[yellow]Server did not stop gracefully. Terminating process...[/yellow]")
                    self.server_process.terminate()
                    try:
                        self.server_process.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        self.server_process.kill()
                
                # Stop log thread
                self.stop_log_thread = True
                if self.log_thread and self.log_thread.is_alive():
                    self.log_thread.join(2)
                
                self.is_running = False
                self.server_process = None
                console.print("[green]Minecraft server stopped.[/green]")
                return True
                
        except Exception as e:
            console.print(f"[red]Error stopping server: {str(e)}[/red]")
            self.is_running = False
            self.server_process = None
            return False
    
    def restart_server(self) -> bool:
        """Restart the Minecraft server."""
        if not self.is_running:
            console.print("[yellow]Server is not running. Starting server...[/yellow]")
            return self.start_server()
            
        console.print("[blue]Restarting Minecraft server...[/blue]")
        
        # Stop the server
        if not self.stop_server():
            console.print("[red]Failed to stop server for restart.[/red]")
            return False
            
        # Short delay to ensure clean shutdown
        time.sleep(2)
        
        # Start the server again
        return self.start_server()
    
    def send_command(self, command: str) -> bool:
        """Send a command to the running Minecraft server."""
        if not self.is_running or not self.server_process:
            console.print("[red]Server is not running. Cannot send command.[/red]")
            return False
            
        try:
            # Add newline to command
            if not command.endswith('\n'):
                command += '\n'
                
            # Send command to server's stdin
            self.server_process.stdin.write(command)
            self.server_process.stdin.flush()
            
            return True
            
        except Exception as e:
            console.print(f"[red]Error sending command: {str(e)}[/red]")
            return False
    
    def _read_server_output(self) -> None:
        """Thread function to read and process server output."""
        while not self.stop_log_thread and self.server_process:
            try:
                if self.server_process.poll() is not None:
                    # Server process has ended
                    break
                    
                line = self.server_process.stdout.readline().strip()
                if line:
                    # Add timestamp if not already present
                    if not re.match(r'^\[\d{2}:\d{2}:\d{2}]', line):
                        timestamp = time.strftime("[%H:%M:%S]")
                        line = f"{timestamp} {line}"
                        
                    # Add to log buffer
                    self.log_buffer.append(line)
                    
                    # Keep buffer at max size
                    if len(self.log_buffer) > self.max_log_lines:
                        self.log_buffer = self.log_buffer[-self.max_log_lines:]
                    
                    # Process specific log messages
                    # Check for tunnel services in logs
                    if "tunnel" in line.lower() or "ngrok" in line.lower() or "playit" in line.lower() or "zrok" in line.lower():
                        # Look for URLs or IPs
                        ip_matches = re.findall(r'\b(?:\d{1,3}\.){3}\d{1,3}(?::\d+)?\b', line)
                        url_matches = re.findall(r'https?://[^\s]+', line)
                        
                        if ip_matches or url_matches:
                            service_name = "unknown"
                            if "ngrok" in line.lower():
                                service_name = "ngrok"
                            elif "playit" in line.lower():
                                service_name = "playit"
                            elif "zrok" in line.lower():
                                service_name = "zrok"
                                
                            self.tunnel_info[service_name] = {
                                "ips": ip_matches,
                                "urls": url_matches,
                                "timestamp": time.time()
                            }
                
            except Exception as e:
                if not self.stop_log_thread:
                    self.log_buffer.append(f"[Error reading server output: {str(e)}]")
                time.sleep(0.1)
                
        # If we exited the loop and the server process has ended, update status
        if self.server_process and self.server_process.poll() is not None:
            self.is_running = False
            self.log_buffer.append("[Server process has ended]")
    
    def edit_config_file(self, file_name: str) -> bool:
        """Open a config file for editing."""
        if not self.server_dir:
            console.print("[red]Server directory is not set.[/red]")
            return False
            
        file_path = self.server_dir / file_name
        
        if not file_path.exists():
            console.print(f"[red]File {file_name} does not exist.[/red]")
            return False
            
        try:
            # Read file content
            with open(file_path, 'r') as f:
                content = f.read()
                
            # Display file for editing
            console.print(Panel(
                Syntax(content, "properties" if file_name.endswith(".properties") else "json", theme="monokai", line_numbers=True),
                title=f"Editing {file_name}",
                subtitle="Press Ctrl+C to cancel editing"
            ))
            
            # Edit mode instructions
            console.print("[yellow]Edit mode:[/yellow] Enter one line at a time. Type ':wq' to save and quit, or ':q' to quit without saving.")
            
            # Edit line by line
            new_lines = content.splitlines()
            quit_without_save = False
            
            try:
                for i, line in enumerate(new_lines):
                    try:
                        new_line = Prompt.ask(f"[{i+1}]", default=line)
                        
                        # Handle special commands
                        if new_line == ":wq":
                            break
                        elif new_line == ":q":
                            quit_without_save = True
                            break
                            
                        new_lines[i] = new_line
                    except KeyboardInterrupt:
                        quit_without_save = True
                        break
            except KeyboardInterrupt:
                quit_without_save = True
                
            if quit_without_save:
                console.print("[yellow]Edit canceled. File not changed.[/yellow]")
                return False
                
            # Ask for confirmation
            if Confirm.ask("Save changes?", default=True):
                # Write back to file
                with open(file_path, 'w') as f:
                    f.write('\n'.join(new_lines))
                console.print(f"[green]Saved changes to {file_name}[/green]")
                
                # Restart server if it's server.properties and server is running
                if file_name == "server.properties" and self.is_running:
                    if Confirm.ask("Restart server to apply changes?", default=True):
                        self.restart_server()
                
                return True
            else:
                console.print("[yellow]Changes not saved.[/yellow]")
                return False
                
        except Exception as e:
            console.print(f"[red]Error editing file: {str(e)}[/red]")
            return False
    
    def get_status(self) -> Dict[str, Any]:
        """Get the current status of the server."""
        status = {
            "running": self.is_running,
            "server_dir": str(self.server_dir) if self.server_dir else None,
            "minecraft_version": self.minecraft_version,
            "mod_loader": self.mod_loader,
            "local_ip": self.local_ip,
            "server_port": self.server_port,
            "tunnel_info": self.tunnel_info,
            "resources": self.resource_usage
        }
        
        # If it's been a while since last check and server is running, update resource usage
        if self.is_running and time.time() - self.last_status_check > 5:
            self._update_resource_usage()
            
        return status
    
    def _update_resource_usage(self) -> None:
        """Update resource usage statistics for the server process."""
        self.last_status_check = time.time()
        
        if not self.is_running or not self.server_process:
            self.resource_usage = {
                "cpu": 0.0,
                "memory": 0,
                "memory_percent": 0.0,
                "uptime": 0,
            }
            return
            
        try:
            # Get process info using psutil
            process = psutil.Process(self.server_process.pid)
            
            # Get CPU and memory usage
            cpu_percent = process.cpu_percent(interval=0.5)
            memory_info = process.memory_info()
            memory_percent = process.memory_percent()
            
            # Get uptime
            uptime = time.time() - process.create_time()
            
            self.resource_usage = {
                "cpu": cpu_percent,
                "memory": memory_info.rss,
                "memory_percent": memory_percent,
                "uptime": uptime,
            }
            
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            # Process has ended or we don't have access
            self.is_running = False
            self.server_process = None
            
        except Exception as e:
            console.print(f"[yellow]Warning: Could not update resource usage: {str(e)}[/yellow]")
    
    def check_tunnel_services(self) -> Dict[str, Any]:
        """Check for running tunnel services."""
        found_tunnels = {}
        
        # For now, we just rely on the tunnel information captured from logs
        # This could be expanded to actively check for tunnel processes
        
        # Look for ngrok
        ngrok_processes = [p for p in psutil.process_iter(['pid', 'name']) 
                          if 'ngrok' in p.info['name'].lower()]
        if ngrok_processes:
            found_tunnels["ngrok"] = {
                "running": True,
                "process_count": len(ngrok_processes)
            }
            
        # Look for playit
        playit_processes = [p for p in psutil.process_iter(['pid', 'name']) 
                           if 'playit' in p.info['name'].lower()]
        if playit_processes:
            found_tunnels["playit"] = {
                "running": True,
                "process_count": len(playit_processes)
            }
            
        # Look for zrok
        zrok_processes = [p for p in psutil.process_iter(['pid', 'name']) 
                         if 'zrok' in p.info['name'].lower()]
        if zrok_processes:
            found_tunnels["zrok"] = {
                "running": True,
                "process_count": len(zrok_processes)
            }
            
        # Update with any info captured from logs
        for service, info in self.tunnel_info.items():
            if service not in found_tunnels:
                found_tunnels[service] = {"running": "unknown"}
            
            found_tunnels[service].update(info)
            
        return found_tunnels

# UI Functions
def display_minecraft_versions():
    """Display a table of available Minecraft versions."""
    table = Table(show_header=True, box=ROUNDED, border_style="green")
    table.add_column("Version", style="cyan")
    table.add_column("Status", style="green")
    
    # Group versions for more compact display
    columns = 3
    rows = (len(MINECRAFT_VERSIONS) + columns - 1) // columns
    
    for i in range(rows):
        row_data = []
        for j in range(columns):
            idx = i + j * rows
            if idx < len(MINECRAFT_VERSIONS):
                row_data.append(MINECRAFT_VERSIONS[idx])
                row_data.append("Available")
            else:
                row_data.append("")
                row_data.append("")
        if any(row_data):  # Only add row if it has data
            table.add_row(*row_data)
    
    console.print(Panel(table, title="Available Minecraft Versions", border_style="green"))

def prompt_for_tunnel_service():
    """Prompt the user to select a tunnel service."""
    console.print(Panel.fit(
        "Select a tunnel service to make your server accessible from the internet:\n\n"
        "1. [bold cyan]ngrok[/bold cyan] - Easy to use, limited in free tier\n"
        "2. [bold cyan]playit.gg[/bold cyan] - Gaming-focused tunneling service\n"
        "3. [bold cyan]zrok[/bold cyan] - Open-source tunneling solution\n"
        "4. None - I'll set this up later",
        title="Tunnel Service Selection",
        border_style="blue"
    ))
    
    choice = Prompt.ask(
        "Select a tunnel service", 
        choices=["1", "2", "3", "4"], 
        default="4"
    )
    
    selected_service = None
    instructions = ""
    
    if choice == "1":
        selected_service = "ngrok"
        instructions = (
            "To use ngrok:\n"
            "1. Download from https://ngrok.com/download\n"
            "2. Run: ngrok tcp 25565\n"
            "3. Copy the URL shown in the ngrok console"
        )
    elif choice == "2":
        selected_service = "playit"
        instructions = (
            "To use playit.gg:\n"
            "1. Download from https://playit.gg/download\n"
            "2. Run the playit executable\n"
            "3. Create a Minecraft Java tunnel"
        )
    elif choice == "3":
        selected_service = "zrok"
        instructions = (
            "To use zrok:\n"
            "1. Download from https://zrok.io\n"
            "2. Run: zrok share tcp:25565\n"
            "3. Copy the URL from the console"
        )
    
    if selected_service:
        console.print(Panel(instructions, title=f"{selected_service.capitalize()} Setup", border_style="green"))
        if Confirm.ask(f"Do you want to set up {selected_service} now?", default=False):
            console.print(f"[yellow]Please set up {selected_service} in another terminal/console, then return here.[/yellow]")
            Prompt.ask("Press Enter when ready to continue", default="")
    
    return selected_service

def create_status_header(manager: MinecraftServerManager) -> Panel:
    """Create a status header panel with resource usage and IP information."""
    status = manager.get_status()
    
    # Main status information
    status_info = f"Status: [green]Running[/green]" if status["running"] else "Status: [red]Stopped[/red]"
    version_info = f"Minecraft [cyan]{status['minecraft_version']}[/cyan] ({status['mod_loader'].capitalize()})"
    
    # Resource usage info
    resource_info = ""
    if status["running"]:
        # Format uptime
        uptime = status["resources"]["uptime"]
        hours, remainder = divmod(int(uptime), 3600)
        minutes, seconds = divmod(remainder, 60)
        uptime_str = f"{hours:02d}:{minutes:02d}:{seconds:02d}"
        
        # Format memory
        memory_mb = status["resources"]["memory"] / (1024 * 1024)
        memory_str = f"{memory_mb:.1f} MB ({status['resources']['memory_percent']:.1f}%)"
        
        resource_info = f"CPU: [yellow]{status['resources']['cpu']:.1f}%[/yellow] | Memory: [yellow]{memory_str}[/yellow] | Uptime: [yellow]{uptime_str}[/yellow]"
    
    # Connection information
    ip_info = f"Local IP: [green]{status['local_ip']}:{status['server_port']}[/green]"
    
    # Tunnel information
    tunnel_info = ""
    if status["tunnel_info"]:
        urls = []
        for service, info in status["tunnel_info"].items():
            if "urls" in info and info["urls"]:
                urls.extend(info["urls"])
            if "ips" in info and info["ips"]:
                urls.extend(info["ips"])
        if urls:
            tunnel_info = f"Public: [green]{urls[0]}[/green]"
    
    # Build the header content
    header_content = Table.grid(padding=1)
    header_content.add_column()
    header_content.add_column()
    
    row1 = [f"{version_info} | {status_info}", ip_info]
    if tunnel_info:
        row1[1] = f"{ip_info} | {tunnel_info}"
    
    header_content.add_row(*row1)
    
    if resource_info:
        header_content.add_row(resource_info, "")
    
    return Panel(header_content, title="Server Information", border_style="blue")

def display_menu():
    """Display the main menu options."""
    table = Table(show_header=False, box=ROUNDED, border_style="blue")
    table.add_column("Option", style="cyan", width=2)
    table.add_column("Action", style="green")
    table.add_column("Description", style="dim")
    
    table.add_row("1", "Start Server", "Launch the Minecraft server")
    table.add_row("2", "Stop Server", "Shutdown the Minecraft server")
    table.add_row("3", "Restart Server", "Restart the Minecraft server")
    table.add_row("4", "View Logs", "View the server logs")
    table.add_row("5", "Send Command", "Send a command to the server")
    table.add_row("6", "Edit Config", "Edit server configuration files")
    table.add_row("7", "Manage Tunnels", "Manage and configure tunnel services")
    table.add_row("8", "Minecraft Versions", "Show available Minecraft versions")
    table.add_row("0", "Exit", "Exit the management panel")
    
    console.print(Panel(table, title="Minecraft Server Management", border_style="blue"))

def display_logs(manager: MinecraftServerManager, max_lines: int = 25):
    """Display the server logs."""
    if not manager.log_buffer:
        console.print("[yellow]No log entries available.[/yellow]")
        return
    
    # Limit the number of lines
    log_lines = manager.log_buffer[-max_lines:] if len(manager.log_buffer) > max_lines else manager.log_buffer
    
    # Format log lines with colors
    formatted_logs = []
    for line in log_lines:
        # Add color highlighting for common log patterns
        if "ERROR" in line or "SEVERE" in line:
            formatted_line = f"[red]{line}[/red]"
        elif "WARN" in line or "WARNING" in line:
            formatted_line = f"[yellow]{line}[/yellow]"
        elif "INFO" in line:
            formatted_line = line  # Default color
        elif "Done" in line and "For help, type" in line:
            formatted_line = f"[green]{line}[/green]"
        else:
            formatted_line = line
        
        formatted_logs.append(formatted_line)
    
    # Join log lines and display
    log_text = "\n".join(formatted_logs)
    console.print(Panel(log_text, title=f"Server Logs (Last {len(log_lines)} entries)", border_style="blue"))
    
    # Option to view more or stream logs
    options = [
        "Return to menu",
        "View more logs" if len(manager.log_buffer) > max_lines else "",
        "Stream logs (press Ctrl+C to stop)"
    ]
    options = [opt for opt in options if opt]  # Remove empty options
    
    choice = Prompt.ask("Select an option", choices=["1", "2", "3"][:len(options)], default="1")
    
    if choice == "2" and len(manager.log_buffer) > max_lines:
        # View more logs
        more_lines = min(100, len(manager.log_buffer))
        display_logs(manager, more_lines)
    elif choice == "3" or (choice == "2" and len(options) == 2):
        # Stream logs
        try:
            console.print("[yellow]Streaming logs... Press Ctrl+C to stop.[/yellow]")
            last_index = len(manager.log_buffer)
            
            while True:
                time.sleep(0.5)
                if len(manager.log_buffer) > last_index:
                    # Print new logs
                    for i in range(last_index, len(manager.log_buffer)):
                        line = manager.log_buffer[i]
                        if "ERROR" in line or "SEVERE" in line:
                            console.print(f"[red]{line}[/red]")
                        elif "WARN" in line or "WARNING" in line:
                            console.print(f"[yellow]{line}[/yellow]")
                        else:
                            console.print(line)
                    last_index = len(manager.log_buffer)
        except KeyboardInterrupt:
            console.print("\n[yellow]Stopped streaming logs.[/yellow]")

def config_file_menu(manager: MinecraftServerManager):
    """Display a menu of configuration files for editing."""
    if not manager.server_dir:
        console.print("[red]Server directory is not set.[/red]")
        return
    
    # Create a table of available config files
    table = Table(show_header=True, box=ROUNDED, border_style="blue")
    table.add_column("#", style="cyan", width=2)
    table.add_column("File", style="green")
    table.add_column("Description", style="dim")
    table.add_column("Exists", style="yellow")
    
    # Find available config files
    config_files = []
    i = 1
    
    for filename, description in CONFIG_FILES.items():
        file_path = manager.server_dir / filename
        exists = file_path.exists()
        
        if exists:
            table.add_row(str(i), filename, description, "[green]Yes[/green]")
            config_files.append(filename)
            i += 1
    
    # Add other config files not in predefined list
    for file_path in manager.server_dir.glob("*.json"):
        if file_path.name not in CONFIG_FILES:
            table.add_row(str(i), file_path.name, "JSON Configuration File", "[green]Yes[/green]")
            config_files.append(file_path.name)
            i += 1
    
    for file_path in manager.server_dir.glob("*.properties"):
        if file_path.name not in CONFIG_FILES:
            table.add_row(str(i), file_path.name, "Properties File", "[green]Yes[/green]")
            config_files.append(file_path.name)
            i += 1
    
    for file_path in manager.server_dir.glob("*.yml"):
        table.add_row(str(i), file_path.name, "YAML Configuration File", "[green]Yes[/green]")
        config_files.append(file_path.name)
        i += 1
    
    console.print(Panel(table, title="Configuration Files", border_style="blue"))
    
    if not config_files:
        console.print("[yellow]No configuration files found.[/yellow]")
        return
    
    # Ask user to select a file
    valid_choices = [str(i) for i in range(1, len(config_files) + 1)]
    choice = Prompt.ask("Select a file to edit (or 0 to return)", choices=["0"] + valid_choices, default="0")
    
    if choice == "0":
        return
    
    # Edit the selected file
    selected_file = config_files[int(choice) - 1]
    manager.edit_config_file(selected_file)

def tunnel_status_display(manager: MinecraftServerManager):
    """Display and manage tunnel services."""
    while True:
        # Clear screen
        if platform.system() == "Windows":
            os.system('cls')
        else:
            os.system('clear')
            
        # Display status header
        console.print(create_status_header(manager))

        # Get updated tunnel info
        tunnels = manager.check_tunnel_services()
        
        # Create a table with tunnel information
        table = Table(show_header=True, box=ROUNDED)
        table.add_column("Service", style="cyan")
        table.add_column("Status", style="green")
        table.add_column("Connection Information", style="yellow")
        
        if tunnels:
            for service, info in tunnels.items():
                status = "[green]Running[/green]" if info.get("running") == True else "[yellow]Unknown[/yellow]"
                
                connection_info = []
                if "urls" in info and info["urls"]:
                    connection_info.extend(info["urls"])
                if "ips" in info and info["ips"]:
                    connection_info.extend(info["ips"])
                    
                connection_text = "\n".join(connection_info) if connection_info else "No connection information available"
                
                table.add_row(service.capitalize(), status, connection_text)
        
            console.print(Panel(table, title="Tunnel Services Status", border_style="blue"))
        else:
            console.print(Panel(
                "[yellow]No tunnel services detected.[/yellow]\n\n"
                "To make your server accessible from the internet, you can set up a tunnel service:\n"
                "- [link=https://ngrok.com]ngrok[/link]: Easy to use, limited in free tier\n"
                "- [link=https://playit.gg]playit.gg[/link]: Gaming-focused tunneling service\n"
                "- [link=https://zrok.io]zrok[/link]: Open-source tunneling solution",
                title="Tunnel Services",
                border_style="yellow"
            ))
        
        # Display management options
        options_table = Table(show_header=False, box=ROUNDED, border_style="blue")
        options_table.add_column("Option", style="cyan", width=2)
        options_table.add_column("Action", style="green")
        
        options_table.add_row("1", "Add new tunnel service")
        options_table.add_row("2", "Edit existing tunnel")
        options_table.add_row("3", "Remove tunnel service")
        options_table.add_row("4", "Setup tunnel service")
        options_table.add_row("5", "Refresh status")
        options_table.add_row("0", "Return to main menu")
        
        console.print(Panel(options_table, title="Tunnel Management", border_style="blue"))
        
        # Get user choice
        choice = Prompt.ask("Select an option", choices=["0", "1", "2", "3", "4", "5"], default="0")
        
        if choice == "0":  # Return to main menu
            break
            
        elif choice == "1":  # Add new tunnel
            service = Prompt.ask("Enter tunnel service name", choices=["ngrok", "playit", "zrok", "custom"], default="custom")
            
            if service == "custom":
                service = Prompt.ask("Enter custom service name")
                
            url = Prompt.ask("Enter tunnel URL or IP (e.g., example.ngrok.io or 123.123.123.123:25565)")
            
            # Categorize as URL or IP
            is_url = "://" in url or url.endswith(".io") or url.endswith(".com") or url.endswith(".net")
            
            # Update tunnel info
            if service not in manager.tunnel_info:
                manager.tunnel_info[service] = {"timestamp": time.time()}
            
            if is_url:
                if "urls" not in manager.tunnel_info[service]:
                    manager.tunnel_info[service]["urls"] = []
                if url not in manager.tunnel_info[service]["urls"]:
                    manager.tunnel_info[service]["urls"].append(url)
            else:
                if "ips" not in manager.tunnel_info[service]:
                    manager.tunnel_info[service]["ips"] = []
                if url not in manager.tunnel_info[service]["ips"]:
                    manager.tunnel_info[service]["ips"].append(url)
            
            console.print(f"[green]Added {url} to {service} tunnel information.[/green]")
            Prompt.ask("Press Enter to continue", default="")
            
        elif choice == "2":  # Edit existing tunnel
            if not manager.tunnel_info:
                console.print("[yellow]No tunnel services to edit.[/yellow]")
                Prompt.ask("Press Enter to continue", default="")
                continue
                
            # List available services
            services = list(manager.tunnel_info.keys())
            if not services:
                console.print("[yellow]No tunnel services found.[/yellow]")
                Prompt.ask("Press Enter to continue", default="")
                continue
                
            # Create options table for services
            service_table = Table(show_header=True, box=ROUNDED)
            service_table.add_column("#", style="cyan", width=3)
            service_table.add_column("Service", style="green")
            
            for i, service in enumerate(services, 1):
                service_table.add_row(str(i), service.capitalize())
                
            console.print(Panel(service_table, title="Select Service to Edit", border_style="blue"))
            
            # Get service selection
            service_idx = Prompt.ask(
                "Select service to edit", 
                choices=[str(i) for i in range(1, len(services) + 1)], 
                default="1"
            )
            selected_service = services[int(service_idx) - 1]
            
            # Get URLs and IPs for this service
            urls = manager.tunnel_info[selected_service].get("urls", [])
            ips = manager.tunnel_info[selected_service].get("ips", [])
            
            # Display current values
            url_table = Table(show_header=True, box=ROUNDED)
            url_table.add_column("#", style="cyan", width=3)
            url_table.add_column("Type", style="blue", width=4)
            url_table.add_column("Value", style="green")
            
            for i, url in enumerate(urls, 1):
                url_table.add_row(str(i), "URL", url)
                
            for i, ip in enumerate(ips, len(urls) + 1):
                url_table.add_row(str(i), "IP", ip)
                
            if urls or ips:
                console.print(Panel(url_table, title=f"URLs and IPs for {selected_service.capitalize()}", border_style="blue"))
                
                # Edit/remove URLs or IPs
                edit_choice = Prompt.ask(
                    "Select an entry to edit/remove or 0 to continue", 
                    choices=["0"] + [str(i) for i in range(1, len(urls) + len(ips) + 1)], 
                    default="0"
                )
                
                if edit_choice != "0":
                    idx = int(edit_choice) - 1
                    if idx < len(urls):
                        # Edit URL
                        url_value = urls[idx]
                        action = Prompt.ask("Edit or Remove?", choices=["Edit", "Remove"], default="Edit")
                        
                        if action == "Edit":
                            new_url = Prompt.ask("Enter new URL", default=url_value)
                            manager.tunnel_info[selected_service]["urls"][idx] = new_url
                            console.print(f"[green]Updated URL to: {new_url}[/green]")
                        else:
                            removed = manager.tunnel_info[selected_service]["urls"].pop(idx)
                            console.print(f"[green]Removed URL: {removed}[/green]")
                    else:
                        # Edit IP
                        ip_idx = idx - len(urls)
                        ip_value = ips[ip_idx]
                        action = Prompt.ask("Edit or Remove?", choices=["Edit", "Remove"], default="Edit")
                        
                        if action == "Edit":
                            new_ip = Prompt.ask("Enter new IP", default=ip_value)
                            manager.tunnel_info[selected_service]["ips"][ip_idx] = new_ip
                            console.print(f"[green]Updated IP to: {new_ip}[/green]")
                        else:
                            removed = manager.tunnel_info[selected_service]["ips"].pop(ip_idx)
                            console.print(f"[green]Removed IP: {removed}[/green]")
            else:
                console.print("[yellow]No URLs or IPs to edit.[/yellow]")
            
            Prompt.ask("Press Enter to continue", default="")
            
        elif choice == "3":  # Remove tunnel service
            if not manager.tunnel_info:
                console.print("[yellow]No tunnel services to remove.[/yellow]")
                Prompt.ask("Press Enter to continue", default="")
                continue
                
            # List available services
            services = list(manager.tunnel_info.keys())
            if not services:
                console.print("[yellow]No tunnel services found.[/yellow]")
                Prompt.ask("Press Enter to continue", default="")
                continue
                
            # Create options table for services
            service_table = Table(show_header=True, box=ROUNDED)
            service_table.add_column("#", style="cyan", width=3)
            service_table.add_column("Service", style="green")
            
            for i, service in enumerate(services, 1):
                service_table.add_row(str(i), service.capitalize())
                
            console.print(Panel(service_table, title="Select Service to Remove", border_style="blue"))
            
            # Get service selection
            service_idx = Prompt.ask(
                "Select service to remove", 
                choices=[str(i) for i in range(1, len(services) + 1)], 
                default="1"
            )
            selected_service = services[int(service_idx) - 1]
            
            if Confirm.ask(f"Are you sure you want to remove {selected_service}?", default=False):
                del manager.tunnel_info[selected_service]
                console.print(f"[green]Removed tunnel service: {selected_service}[/green]")
            else:
                console.print("[yellow]Removal cancelled.[/yellow]")
                
            Prompt.ask("Press Enter to continue", default="")
            
        elif choice == "4":  # Setup tunnel service
            selected_service = prompt_for_tunnel_service()
            if selected_service:
                console.print(f"[green]Selected tunnel service: {selected_service}[/green]")
                Prompt.ask("Press Enter to continue", default="")
            
        elif choice == "5":  # Refresh status
            manager._update_resource_usage()
            console.print("[green]Status refreshed.[/green]")
            Prompt.ask("Press Enter to continue", default="")

def display_status(manager: MinecraftServerManager):
    """Display the current server status."""
    status = manager.get_status()
    
    # Create status panels
    server_info_table = Table(show_header=True, box=ROUNDED)
    server_info_table.add_column("Setting", style="blue")
    server_info_table.add_column("Value", style="green")
    
    # Add basic server info
    server_info_table.add_row("Status", "[green]Running[/green]" if status["running"] else "[red]Stopped[/red]")
    server_info_table.add_row("Minecraft Version", status["minecraft_version"])
    server_info_table.add_row("Mod Loader", status["mod_loader"].capitalize())
    server_info_table.add_row("Server Directory", status["server_dir"])
    
    # Add connection info
    server_info_table.add_row("Local IP", f"{status['local_ip']}:{status['server_port']}")
    
    # Add resource usage if server is running
    if status["running"]:
        # Format uptime
        uptime = status["resources"]["uptime"]
        hours, remainder = divmod(int(uptime), 3600)
        minutes, seconds = divmod(remainder, 60)
        uptime_str = f"{hours:02d}:{minutes:02d}:{seconds:02d}"
        
        # Format memory
        memory_mb = status["resources"]["memory"] / (1024 * 1024)
        memory_str = f"{memory_mb:.1f} MB ({status['resources']['memory_percent']:.1f}%)"
        
        server_info_table.add_row("CPU Usage", f"{status['resources']['cpu']:.1f}%")
        server_info_table.add_row("Memory Usage", memory_str)
        server_info_table.add_row("Uptime", uptime_str)
    
    # Tunnel information
    tunnel_table = None
    if status["tunnel_info"]:
        tunnel_table = Table(show_header=True, box=ROUNDED)
        tunnel_table.add_column("Tunnel Service", style="cyan")
        tunnel_table.add_column("Access URLs/IPs", style="green")
        
        for service, info in status["tunnel_info"].items():
            urls = ""
            if "urls" in info and info["urls"]:
                urls += "\n".join(info["urls"])
            if "ips" in info and info["ips"]:
                if urls:
                    urls += "\n"
                urls += "\n".join(info["ips"])
                
            if urls:
                tunnel_table.add_row(service.capitalize(), urls)
    
    # Display the information in panels
    console.print(Panel(server_info_table, title="Server Status", border_style="blue"))
    
    if tunnel_table:
        console.print(Panel(tunnel_table, title="Tunnel Services", border_style="cyan"))
    else:
        console.print("[yellow]No tunnel services detected. Players can only connect from your local network.[/yellow]")

def main():
    """Main function to run the server management panel."""
    console.print(Panel.fit(
        "[bold blue]Minecraft Server Management Panel[/bold blue]\n\n"
        "This tool helps you manage your Minecraft server with a user-friendly interface.\n"
        "You can start/stop the server, view logs, edit configuration files, and more.",
        border_style="blue"
    ))
    
    # Display available Minecraft versions
    display_minecraft_versions()
    
    # Initialize server manager
    manager = MinecraftServerManager()
    
    # Load server information
    if not manager.load_server_info():
        console.print("[red]Failed to load server information. Make sure you have a valid Minecraft server installed.[/red]")
        
        # Ask if the user wants to browse for a server directory manually
        if Confirm.ask("Would you like to manually locate your server directory?", default=True):
            server_dir = Prompt.ask(
                "Enter the full path to your Minecraft server directory",
                default=str(Path.home() / "minecraft_server")
            )
            
            if not Path(server_dir).exists():
                if Confirm.ask(f"Directory {server_dir} does not exist. Create it?", default=True):
                    try:
                        Path(server_dir).mkdir(parents=True, exist_ok=True)
                        console.print(f"[green]Created directory: {server_dir}[/green]")
                    except Exception as e:
                        console.print(f"[red]Failed to create directory: {str(e)}[/red]")
                        return
                else:
                    console.print("[yellow]Setup canceled.[/yellow]")
                    return
                    
            # Set up basic server info
            manager.server_dir = Path(server_dir)
            
            # Check for JAR files
            jar_files = list(Path(server_dir).glob("*.jar"))
            if jar_files:
                # Select a JAR file
                if len(jar_files) > 1:
                    console.print("[yellow]Multiple JAR files found. Please select one:[/yellow]")
                    for i, jar in enumerate(jar_files, 1):
                        console.print(f"[cyan]{i}[/cyan]: {jar.name}")
                    
                    jar_choice = Prompt.ask("Select JAR file", choices=[str(i) for i in range(1, len(jar_files) + 1)], default="1")
                    selected_jar = jar_files[int(jar_choice) - 1]
                else:
                    selected_jar = jar_files[0]
                
                manager.main_jar = str(selected_jar.relative_to(manager.server_dir))
                console.print(f"[green]Selected JAR file: {manager.main_jar}[/green]")
            else:
                console.print("[yellow]No JAR files found in the selected directory.[/yellow]")
                console.print("[yellow]You'll need to obtain a Minecraft server JAR file.[/yellow]")
                return
                
            # Find Java
            manager.java_executable = shutil.which("java")
            if not manager.java_executable:
                console.print("[red]Java not found! Please install Java before running the server.[/red]")
                return
                
            # Create minimal server info
            manager.server_info = {
                "server_dir": str(manager.server_dir),
                "main_jar": manager.main_jar,
                "java_executable": manager.java_executable,
                "minecraft_version": "unknown",
                "mod_loader": "vanilla",
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            }
            
            # Try to detect mod loader from JAR name
            jar_name = manager.main_jar.lower()
            if "forge" in jar_name:
                manager.mod_loader = "forge"
                manager.server_info["mod_loader"] = "forge"
            elif "fabric" in jar_name:
                manager.mod_loader = "fabric"
                manager.server_info["mod_loader"] = "fabric"
            elif "quilt" in jar_name:
                manager.mod_loader = "quilt"
                manager.server_info["mod_loader"] = "quilt"
            elif "neoforge" in jar_name:
                manager.mod_loader = "neoforge"
                manager.server_info["mod_loader"] = "neoforge"
            
            # Save the server info
            manager._save_server_info()
            console.print("[green]Basic server information set up successfully.[/green]")
            
            # Prompt for tunnel service
            selected_service = prompt_for_tunnel_service()
            if selected_service:
                console.print(f"[green]Selected tunnel service: {selected_service}[/green]")
        else:
            console.print("[yellow]Exiting. Please set up a Minecraft server before using this tool.[/yellow]")
            return
    
    # Check if the server is already running
    try:
        # Try to find a running Java process that looks like a Minecraft server
        for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
            try:
                if proc.info['name'].lower() in ('java', 'java.exe') and proc.info['cmdline']:
                    cmdline = ' '.join(proc.info['cmdline'])
                    # Check if it's a Minecraft server using our JAR
                    if manager.main_jar in cmdline and '-jar' in cmdline:
                        console.print(f"[yellow]Found a running Minecraft server process (PID: {proc.info['pid']})[/yellow]")
                        if Confirm.ask("Do you want to attach to this running server?", default=True):
                            # Initialize server process
                            manager.server_process = psutil.Process(proc.info['pid'])
                            manager.is_running = True
                            
                            # Start log reading thread (this won't work fully with an existing process)
                            manager.log_buffer.append("[System] Attached to running server.")
                            manager._update_resource_usage()
                            break
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                continue
    except Exception as e:
        console.print(f"[yellow]Warning: Could not check for running server: {str(e)}[/yellow]")
    
    # If server is set up properly but no tunnel has been selected yet, prompt for it
    if not manager.tunnel_info:
        selected_service = prompt_for_tunnel_service()
        if selected_service:
            console.print(f"[green]Selected tunnel service: {selected_service}[/green]")
    
    # Main program loop
    running = True
    while running:
        # Clear screen for Windows
        if platform.system() == "Windows":
            os.system('cls')
        else:
            os.system('clear')
            
        # Update resource usage before displaying header
        manager._update_resource_usage()
        
        # Display the enhanced status header
        console.print(create_status_header(manager))
        console.print(f"[dim]Server directory: {manager.server_dir}[/dim]")
        
        # Display main menu
        display_menu()
        
        # Get user choice
        choice = Prompt.ask("Select an option", choices=["0", "1", "2", "3", "4", "5", "6", "7", "8", "9"], default="4")
        
        # Process user choice
        try:
            if choice == "0":  # Exit
                running = False
                if manager.is_running:
                    if Confirm.ask("Server is still running. Stop it before exiting?", default=True):
                        manager.stop_server()
            
            elif choice == "1":  # Start Server
                if not manager.is_running:
                    manager.start_server()
                else:
                    console.print("[yellow]Server is already running.[/yellow]")
                    Prompt.ask("Press Enter to continue", default="")
            
            elif choice == "2":  # Stop Server
                if manager.is_running:
                    manager.stop_server()
                else:
                    console.print("[yellow]Server is not running.[/yellow]")
                    Prompt.ask("Press Enter to continue", default="")
            
            elif choice == "3":  # Restart Server
                manager.restart_server()
            
            elif choice == "4":  # Server Status
                display_status(manager)
                Prompt.ask("Press Enter to return to menu", default="")
            
            elif choice == "5":  # View Logs
                display_logs(manager)
            
            elif choice == "6":  # Send Command
                if not manager.is_running:
                    console.print("[red]Server is not running. Cannot send commands.[/red]")
                    Prompt.ask("Press Enter to continue", default="")
                else:
                    console.print(Panel(
                        "Type commands to send to the server. Type 'exit' to return to the menu.",
                        title="Server Console",
                        border_style="green"
                    ))
                    
                    # Display recent logs for context
                    recent_logs = manager.log_buffer[-5:] if len(manager.log_buffer) >= 5 else manager.log_buffer
                    for log in recent_logs:
                        console.print(log)
                    
                    # Command input loop
                    while True:
                        command = Prompt.ask("> ")
                        if command.lower() == 'exit':
                            break
                        
                        if manager.send_command(command):
                            # Wait briefly for response in logs
                            time.sleep(0.5)
                            # Show any new logs
                            new_logs = manager.log_buffer[-1:] if manager.log_buffer else []
                            for log in new_logs:
                                console.print(log)
                        else:
                            console.print("[red]Failed to send command. Server may have stopped.[/red]")
                            break
            
            elif choice == "7":  # Edit Config
                config_file_menu(manager)
            
            elif choice == "8":  # Check Tunnels
                tunnel_status_display(manager)
                Prompt.ask("Press Enter to return to menu", default="")
            
            elif choice == "9":  # Minecraft Versions
                display_minecraft_versions()
                Prompt.ask("Press Enter to continue", default="")
        
        except KeyboardInterrupt:
            console.print("\n[yellow]Operation cancelled.[/yellow]")
            time.sleep(1)
        except Exception as e:
            console.print(f"[red]Error: {str(e)}[/red]")
            console.print("[yellow]Press Enter to continue[/yellow]")
            input()
    
    # Clean up before exit
    console.print("[blue]Exiting Minecraft Server Manager...[/blue]")
    if manager.is_running:
        console.print("[yellow]Warning: Server is still running in the background.[/yellow]")
    
    # Stop log thread if it's running
    if manager.log_thread and manager.log_thread.is_alive():
        manager.stop_log_thread = True
        manager.log_thread.join(2)
    
    console.print("[green]Thank you for using Minecraft Server Manager![/green]")

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        console.print("\n[yellow]Program interrupted. Exiting...[/yellow]")
    except Exception as e:
        console.print(f"[red]Unhandled error: {str(e)}[/red]")
        import traceback
        console.print(traceback.format_exc())
    sys.exit(0)
