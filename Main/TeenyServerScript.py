import glob
import json
import os
import platform
import shutil
import subprocess
from threading import Thread

import minecraft_launcher_lib as mllb
import jdk
import requests
from pyngrok import conf, ngrok


print("This script was made by TeenyDesert9892")


def load_config():
    jsonConfig = open("server_config.json", "r")
    global config
    config = json.load(jsonConfig)


def save_config():
    jsonConfig = open("server_config.json", "w")
    global config
    json.dump(config, jsonConfig, indent=4)


def is_program_installed(program_name=str):
    if platform.system() == "Windows":
        command = f"where {program_name}"
    else:
        command = f"which {program_name}"
    result = subprocess.run(command, shell=True, stdout=subprocess.PIPE)
    return result.returncode == 0


def install_program(url=str, fileName=str):
    javaRequest = requests.get(url)
    if javaRequest.status_code == 200:
        with open(f'{fileName}', 'wb') as file:
            file.write(javaRequest.content)
    else:
        print('Error ' + str(javaRequest.status_code))

    subprocess.run(f"{fileName}", shell=True)
    subprocess.run(f"del {fileName}", shell=True)


def get_jdk_version(server_version=str):
    if float(server_version.replace(".", "", 1)) >= 120.5:
        return "21"
    elif float(server_version.replace(".", "", 1)) >= 118:
        return "17"
    elif float(server_version.replace(".", "", 1)) >= 117:
        return "16"
    else:
        return "8"


def get_jdk_server(jdk_version=str):
    if not os.path.exists("assets/jdks"):
        os.mkdir("assets/jdks")

    try:
        try:
            return os.path.normpath(f"{os.getcwd()}/{glob.glob('assets/jdks/jdk' + jdk_version + '*')[0]}")
        except:
            jdk.install(version=jdk_version, operating_system=jdk.OperatingSystem.detect(), arch=jdk.Architecture.detect(), jre=False, path=os.path.normpath(f"{os.getcwd()}/assets/jdks"))
            return os.path.normpath(f"{os.getcwd()}/{glob.glob('assets/jdks/jdk' + jdk_version + '*')[0]}")
    except:
        try:
            return os.path.normpath(f"{os.getcwd()}/{glob.glob('assets/jdks/jdk-' + jdk_version + '*')[0]}")
        except:
            jdk.install(version=jdk_version, operating_system=jdk.OperatingSystem.detect(), arch=jdk.Architecture.detect(), jre=False, path=os.path.normpath(f"{os.getcwd()}/assets/jdks"))
            return os.path.normpath(f"{os.getcwd()}/{glob.glob('assets/jdks/jdk-' + jdk_version + '*')[0]}")


def create_server():
    server_version = config[0]["server_version"]
    server_type = config[0]["server_type"]
    folder_name = config[0]["folder_name"]

    print("Verificando si esta instalada la version correcta de jdk")
    jdk_version = get_jdk_version(server_version)
    jdk_folder = get_jdk_server(jdk_version)

    if platform.system() == "Windows":
        jdk_run = os.path.normpath(jdk_folder + "/bin/java.exe")
    else:
        jdk_run = os.path.normpath(jdk_folder + "/bin/java")

    try:
        if not os.path.exists(f"{folder_name}"):
            os.mkdir(f"{folder_name}")

        print('Descargando a archivos del servidor...')

        serverURL = ""

        if server_type == 'paper':
            serverURL = "https://jar.smd.gg/download/paper/" + server_version + "/latest"

        elif server_type == 'spigot':
            if not os.path.exists("assets/BuildTools/BuildTools.jar"):
                buildTools = requests.get("https://hub.spigotmc.org/jenkins/job/BuildTools/lastSuccessfulBuild/artifact/target/BuildTools.jar")
                if buildTools.status_code == 200:
                    if not os.path.exists("assets/BuildTools"):
                        os.mkdir("assets/BuildTools")
                    with open("assets/BuildTools/BuildTools.jar", "wb") as file:
                        file.write(buildTools.content)
                        file.close()
            os.chdir("assets/BuildTools")
            subprocess.run(f"{jdk_run} -jar BuildTools.jar --rev " + server_version)
            os.chdir("..")
            os.chdir("..")
            shutil.move(f"assets/BuildTools/spigot-{server_version}.jar", folder_name)
            os.rename(folder_name + f"/spigot-{server_version}.jar", f"{folder_name}/spigot.jar")

        elif server_type == 'mohist':
            url = requests.get("https://mohistmc.com/api/v2/projects/mohist")
            if url.status_code == 200:
                for version in str(url.content).replace("b", "").replace("{", "").replace("}", "").replace("[", "").replace("]", "").replace('"', '').replace("'", "").split(":")[1].split(","):
                    if version == server_version:
                        getBuilds = requests.get("https://mohistmc.com/api/v2/projects/mohist/" + server_version + "/builds")
                        if getBuilds.status_code == 200:
                            with open("builds.json", "wb") as file:
                                file.write(getBuilds.content)
                                file.close()
                        buildsFile = open("builds.json", "r")
                        builds = json.load(buildsFile)
                        buildsFile.close()
                        os.remove("builds.json")
                        bestBuild = 0
                        for build in builds["builds"]:
                            if build["number"] > bestBuild:
                                bestBuild = build["number"]
                                serverURL = build["url"]

        elif server_type == 'forge':
            forgeVersion = mllb.forge.find_forge_version(server_version)
            serverURL = "https://maven.minecraftforge.net/net/minecraftforge/forge/" + forgeVersion + "/forge-" + forgeVersion + "-installer.jar"

        elif server_type == 'vanilla':
            serverURL = "https://jar.smd.gg/download/vanilla/" + server_version

        elif server_type == 'fabric':
            serverURL = 'https://maven.fabricmc.net/net/fabricmc/fabric-installer/1.0.1/fabric-installer-1.0.1.jar'

        else:
            print("El tipo de version que seleccionaste no es valido")

        jar_list = {'paper': 'server.jar', 'fabric': 'fabric-installer.jar', 'mohist': 'mohist.jar', 'spigot': 'spigot.jar',
                    'generic': 'server.jar', 'forge': 'mohist.jar', 'vanilla': 'vanilla.jar', 'snapshot': 'snapshot.jar'}

        jar_name = jar_list[server_type]

        os.chdir(folder_name)

        if server_type != 'spigot':
            request = requests.get(serverURL)
            if request.status_code == 200:
                with open(f'{jar_name}', 'wb') as file:
                    file.write(request.content)
                    file.close()
            elif request.status_code == 502:
                print('Error: ' + str(request.status_code) + "! La pagina se ha caido temporalmente prueba mas tarde...")
            else:
                print('Error: ' + str(request.status_code) + '! La versión que has elegido probablemente no funciona / Puede ser que hallas introducido una version inexistente. Prueba a ejecutar el codigo otra vez por si acaso fue un pequeño error.')

        if server_type == 'fabric':
            subprocess.run(f"{jdk_run} -jar fabric-installer.jar server --mcversion ${server_version} --downloadMinecraft", shell=True)
            minecraft_server_base = requests.get("https://jar.smd.gg/download/vanilla/" + server_version)
            os.remove("fabric-installer.jar")
            if minecraft_server_base.status_code == 200:
                with open("server.jar", "wb") as jar:
                    jar.write(minecraft_server_base.content)
                    jar.close()

        if server_type == 'forge':
            subprocess.run(f"{jdk_run} -jar forge.jar --installServer", shell=True)

        print("Completado!")
        subprocess.run("echo eula=true>> eula.txt", shell=True)

        print("\n____________________AVISO!!!____________________\nSe ha creado un nuevo archivo al lado de TeenyServerScript llamado server_config.json\nSe recomienda mirarlo antes de iniciar el servidor por primera vez para saber que contiene\nCualquer cambio puede dañar al funcionamiento del servidor asi que sea delicado")
    except:
        if os.path.exists(folder_name):
            shutil.rmtree(folder_name)

        if os.path.exists("server_config.json"):
            os.remove("server_config.json")

        print("\nAlguno de los datos que has introducido es invalido\nDeteniendo el script...")


def start_server():
    server_version = config[0]["server_version"]
    server_type = config[0]["server_type"]
    folder_name = config[0]["folder_name"]
    max_ram = config[0]["max_ram"]
    connect_service = config[1]["connect_service"]
    ngrok_token = config[1]["ngrok_token"]
    ngrok_region = config[1]["ngrok_region"]

    print("Verificando si esta instalada la version correcta de jdk")
    jdk_version = get_jdk_version(server_version)
    jdk_folder = get_jdk_server(jdk_version)

    if platform.system() == "Windows":
        jdk_run = os.path.normpath(jdk_folder + "/bin/javaw.exe")
    else:
        jdk_run = os.path.normpath(jdk_folder + "/bin/java")

    if os.path.exists(f"{folder_name}"):
        os.chdir(f"{folder_name}")

        print(f"Estas usando la version de java: {jdk_version}")

        jar_list = {'paper': 'server.jar', 'fabric': 'fabric-server-launch.jar', 'mohist': 'mohist.jar', 'spigot': 'spigot.jar',
                    'generic': 'server.jar', 'forge': 'mohist.jar', 'vanilla': 'vanilla.jar', 'snapshot': 'snapshot.jar'}

        jar_name = jar_list[server_type]

        if server_type == "paper":
            server_flags = "-XX:+UseG1GC -XX:+ParallelRefProcEnabled -XX:MaxGCPauseMillis=200 -XX:+UnlockExperimentalVMOptions -XX:+DisableExplicitGC -XX:+AlwaysPreTouch -XX:G1NewSizePercent=30 -XX:G1MaxNewSizePercent=40 -XX:G1HeapRegionSize=8M -XX:G1ReservePercent=20 -XX:G1HeapWastePercent=5 -XX:G1MixedGCCountTarget=4 -XX:InitiatingHeapOccupancyPercent=15 -XX:G1MixedGCLiveThresholdPercent=90 -XX:G1RSetUpdatingPauseTimePercent=5 -XX:SurvivorRatio=32 -XX:+PerfDisableSharedMem -XX:MaxTenuringThreshold=1 -Dusing.aikars.flags=https://mcflags.emc.gs -Daikars.new.flags=true"
        else:
            server_flags = ""
        memory_allocation = f"-Xms512M {max_ram}"

        if platform.system() == "Windows":
            subprocess.run("cls", shell=True)
        else:
            subprocess.run("clear", shell=True)

        if connect_service == "n":
            print('\nIniciando servidor con ngrok...')

            subprocess.run(f"ngrok authtoken {ngrok_token}", shell=True)
            conf.get_default().region = ngrok_region

            urlj = ngrok.connect('25565', 'tcp')
            print('La IP de tu servidor de java es ' + ((str(urlj).split('"')[1::2])[0]).replace('tcp://', ''))
            if os.path.exists(str(f"{os.getcwd()}/plugins/Geyser-Spigot.jar")):
                urlb = ngrok.connect('19132', 'tcp')
                print('La IP de tu servidor e bedrock es ' + ((str(urlb).split('"')[1::2])[0]).replace('tcp://', ''))

            launch_server(memory_allocation, server_flags, jar_name, jdk_run)

        elif connect_service == "p":
            print('\nIniciando servidor con playit...')

            if not is_program_installed("playit"):
                if platform.system() == "Windows":
                    install_program("https://github.com/playit-cloud/playit-agent/releases/download/v0.15.13/playit-windows-x86_64-signed.msi","playit-windows-x86_64-signed.msi")
                else:
                    subprocess.run("curl -SsL https://playit-cloud.github.io/ppa/key.gpg | sudo apt-key add -", shell=True)
                    subprocess.run("sudo curl -SsL -o /etc/apt/sources.list.d/playit-cloud.list https://playit-cloud.github.io/ppa/playit-cloud.list", shell=True)
                    subprocess.run("sudo apt update &>/dev/null && sudo apt install playit &>/dev/null && echo 'Playit.gg instalado' || echo 'Error al instalar playit'", shell=True)

            def playit():
                subprocess.run("playit")

            playitThread = Thread(target=playit, daemon=True)
            playitThread.start()

            launch_server(memory_allocation, server_flags, jar_name, jdk_run)

        elif connect_service == "l":
            print('\nIniciando servidor en localhost...')
            launch_server(memory_allocation, server_flags, jar_name, jdk_run)
        else:
            print("Servicio desconocido, el servidor no iniciara")
    else:
        print("\nAun no tienes ningun servidor creado")


def launch_server(memory_allocation=str, server_flags=str, jar_name=str, jdk=None):
    server_type = config[0]["server_type"]
    server_version = config[0]["server_version"]

    if server_type == "forge":
        if float(server_version.replace(".", "", 1)) < 117:
            oldpathtoforge = glob.glob(f"forge-{server_version}-*.jar")
            if oldpathtoforge:
                path = oldpathtoforge[0]
                try:
                    subprocess.run(f"{jdk} {memory_allocation} -jar {path}", shell=True)
                except:
                    subprocess.run(f"'{jdk}' {memory_allocation} -jar {path}", shell=True)
            else:
                print("No ha sido encontrado 'forge universal jar'")
        else:
            pathtoforge = glob.glob(f"libraries/net/minecraftforge/forge/{server_version}-*/unix_*.txt")
            if pathtoforge:
                path = pathtoforge[0]
                try:
                    subprocess.run(f"{jdk} @user_jvm_args.txt @{path} $@", shell=True)
                except:
                    subprocess.run(f"'{jdk}' @user_jvm_args.txt @{path} $@", shell=True)
            else:
                print("No ha sido encontrado 'unix_args.txt'")
    else:
        try:
            subprocess.run(f"{jdk} {memory_allocation} {server_flags} -jar {jar_name}", shell=True)
        except:
            subprocess.run(f"'{jdk}' {memory_allocation} {server_flags} -jar {jar_name}", shell=True)


def read_message(msg=str):
    with open(f'assets/messages/{msg}.txt', 'r') as file: return file.read()


def create_server_menu():
    server_type_message = read_message("server_type")
    server_version_message = read_message("server_version")
    max_ram_message = read_message("max_ram")
    folder_name_message = read_message("folder_name")
    connect_service_message = read_message("connect_service")

    server_type = input(f"\n{server_type_message} ")
    server_version = input(f"\n{server_version_message} ")
    max_ram = "-Xmx"+input(f"\n{max_ram_message} ")+"G"
    folder_name = input(f"\n{folder_name_message} ").replace(" ", "-")
    connect_service = input(f"\n{connect_service_message} ")

    if connect_service == "n":
        ngrok_token_message = read_message("ngrok_token")
        ngrok_region_message = read_message("ngrok_region")

        ngrok_token = input(f"\n{ngrok_token_message} ")
        ngrok_region = input(f"\n{ngrok_region_message} ")

    elif connect_service == "p" or connect_service == "l":
        ngrok_token = ""
        ngrok_region = "eu"

    else:
        print("\nNo se especifico el servicio de manera correcta, por defecto en local")
        connect_service = "l"
        ngrok_token = ""
        ngrok_region = "eu"

    if folder_name == "assets":
        folder_name = "Server"

    config[0]["server_type"] = server_type
    config[0]["server_version"] = server_version
    config[0]["max_ram"] = max_ram
    config[0]["folder_name"] = folder_name
    config[1]["connect_service"] = connect_service
    config[1]["ngrok_token"] = ngrok_token
    config[1]["ngrok_region"] = ngrok_region

    save_config()

    if platform.system() == "Windows":
        subprocess.run("cls", shell=True)
    else:
        subprocess.run("clear", shell=True)

    create_server()


def configure_options():
    if os.path.exists("server_config.json"):
        option = input("\nSelect the option you want to edit:\n(1) Change server Ram\n(2) Change folder name\n(3) Change service type\n(4) Delete current server\n>>> ")
        if option == "1":
            max_ram_message = read_message("max_ram")
            config[0]["max_ram"] = "-Xmx"+input(f"\n {max_ram_message} ")+"G"
        elif option == "2":
            folder_name_message = read_message("folder_name")
            config[0]["folder_name"] = input(f"\n {folder_name_message} ")
        elif option == "3":
            connect_service_message = read_message("connect_service")
            config[1]["connect_service"] = input(f"\n {connect_service_message} ")

            if config[1]["connect_service"] == "n":
                ngrok_token_message = read_message("ngrok_token")
                ngrok_region_message = read_message("ngrok_region")

                config[1]["ngrok_token"] = input(f"\n{ngrok_token_message} ")
                config[1]["ngrok_region"] = input(f"\n{ngrok_region_message} ")
            elif config[1]["connect_service"] == "p" or config[1]["connect_service"] == "l":
                config[1]["ngrok_token"] = ""
                config[1]["ngrok_region"] = "eu"
            else:
                print("\nNo se especifico el servicio de manera correcta, por defecto en local")
                config[1]["connect_service"] = "l"
                config[1]["ngrok_token"] = ""
                config[1]["ngrok_region"] = "eu"
        elif option == "4":
            confirm_delete = input("Estas seguro de que quieres eliminar el servidor? (y/n): ").lower()
            if confirm_delete == "y":
                shutil.rmtree(config[0]["folder_name"])
                os.remove("server_config.json")
        else:
            print("\nOpcion no valida")
        save_config()
    else:
        print("No has creado ningun servidor aun")


if __name__ == "__main__":
    if platform.system() == "Windows":
        subprocess.run("cls", shell=True)
    else:
        subprocess.run("clear", shell=True)

    try:
        load_config()
    except:
        config = [{"server_type": "", "server_version": "", "max_ram": "", "folder_name": ""}, {"connect_service": "", "ngrok_token": "", "ngrok_region": ""}]

    logo = read_message("logo")

    print(logo)
    selection = input("\nOpciones para iniciar el servidor:\n(1) Instalar un servidor\n(2) Inicar el servidor (primero usa el 1)\n(3) Configurar opciones del servidor\n>>> ")

    if platform.system() == "Windows":
        subprocess.run("cls", shell=True)
    else:
        subprocess.run("clear", shell=True)

    if selection == "1":
        create_server_menu()
    elif selection == "2":
        start_server()
    elif selection == "3":
        configure_options()
    else:
        print("\nSeleccion no valida")