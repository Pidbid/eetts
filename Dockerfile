FROM python:3.12.9-slim

WORKDIR /app

# 只复制必要的文件
COPY eetts.sh eetts.py requirements.txt ./

RUN mkdir /output && chmod 755 /output

RUN chmod +x eetts.sh

EXPOSE 8000

ENV TOKEN=eetts

CMD ["/app/eetts.sh"]