from flask import Flask, request, make_response
import hashlib
import time
import os

app = Flask(__name__)

@app.route('/wechat', methods=['GET', 'POST'])
def wechat():
    if request.method == 'GET':
        signature = request.args.get('signature')
        timestamp = request.args.get('timestamp')
        nonce = request.args.get('nonce')
        echostr = request.args.get('echostr')
        token = 'yeki'
        tmp_list = [token, timestamp, nonce]
        tmp_list.sort()
        tmp_str = ''.join(tmp_list)
        hashcode = hashlib.sha1(tmp_str.encode('utf-8')).hexdigest()
      
        # 调试：打印计算出的签名和微信提供的签名
        #print(f"计算的签名: {hashcode}")
        #print(f"微信提供的签名: {signature}")
      
        print(f"微信签名：{signature}")
        print(f"计算签名：{hashcode}")
        print("== 微信请求进入 ==")
        print("参数如下：")
        print("signature:", signature)
        print("timestamp:", timestamp)
        print("nonce:", nonce)
        print("echostr:", echostr)
        print("== 微信请求进来了 ==")
        print("全部参数如下：", request.args.to_dict())


        if hashcode == signature:
            return echostr
        else:
            return '验证失败'

       

    else:
        return '暂未处理 POST'
    
@app.route('/test')
def test():
    return "服务正常！"


# 线上环境不需要 `app.run()`，Render 会使用 gunicorn 直接调用 app 实例
