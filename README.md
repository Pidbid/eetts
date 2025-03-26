# eetts
An edge tts server in docker.

## How to start a docker
- clone eets project
  - git clone https://github.com/Pidbid/eetts.git  
- cd eets 
- start a docker 
  - docker run -itd -p 8000:8000 -v ./output:output -e TOKEN={{your_token}} wicos/eetts:latest

## How to use
you can view http://{ip}:{port}/docs