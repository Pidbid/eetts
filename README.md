# eetts
An edge tts server in docker.

## How to start

### Docker
- docker run -itd -p 8000:8000 -v ./output:output -e TOKEN={{your_token}} wicos/eetts:latest

### General
- git clone https://github.com/Pidbid/eetts.git  
- cd eets 
- python3 -m venv env
- Activate the env
- pip install -r ./requirements.txt  
- python3 ./eetts.py

## How to use
you can view http://{ip}:{port}/docs