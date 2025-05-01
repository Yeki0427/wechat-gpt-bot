from flask import Flask, request, make_response
import hashlib
import time
import os

app = Flask(__name__)

@app.route('/wechat', methods=['GET', 'POST'])
def wechat():
    if request.method == 'GET':
        token = os.environ.get("TOKEN", "yeki")
        signature = request.args.get('signature')
        timestamp = request.args.get('timestamp')
        nonce = request.args.get('nonce')
        echostr = request.args.get('echostr')
        if not all([signature, timestamp, nonce, echostr]):
            return '缺参数'

        tmp_list = [token, timestamp, nonce]
        tmp_list.sort()
        tmp_str = ''.join(tmp_list)
        hashcode = hashlib.sha1(tmp_str.encode('utf-8')).hexdigest()

        print(f"微信签名：{signature}")
        print(f"计算签名：{hashcode}")

        if hashcode == signature:
            return echostr
        else:
            return '验证失败'
    else:
        return '暂未处理 POST'

# 线上环境不需要 `app.run()`，Render 会使用 gunicorn 直接调用 app 实例
