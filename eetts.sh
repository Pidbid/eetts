#!/bin/bash
if wget -q --spider -T 10 http://www.google.com; then
    echo "Detected location: Outside China"
    pip install --no-cache-dir -r requirements.txt 
else
    echo "Detected location: China"
    pip install --no-cache-dir -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
fi
python eetts.py