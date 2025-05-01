from flask import Flask, request, make_response
import xml.etree.ElementTree as ET
import time
import hashlib
from openai import OpenAI
from collections import defaultdict
import csv
import os
from datetime import datetime
import json

# 隐藏 Flask 的访问请求日志
import logging
log = logging.getLogger('werkzeug')
log.setLevel(logging.ERROR)


# 聊天记录 sessions
sessions = defaultdict(list)
completed_users = set()
verify_codes = {}

# 每个用户的轮次计数器
rounds = defaultdict(int)

client = OpenAI()

with open("prompt.txt", "r", encoding="utf-8") as f:
    system_prompt = f.read()

# 创建 Flask 应用
app = Flask(__name__)


@app.route('/wechat', methods=['GET', 'POST'])
def wechat():
    if request.method == 'GET':
        # 微信服务器验证
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

        if hashcode == signature:
            return echostr
        else:
            return '验证失败'
        
    # 收到用户发来的消息
    elif request.method == 'POST':
        
        start = time.time()

        xml_data = request.data
        root = ET.fromstring(xml_data)
        user_msg = root.find('Content').text.strip()
        to_user = root.find('FromUserName').text
        from_user = root.find('ToUserName').text

        rounds[to_user] += 1
        print(f"[微信用户 {to_user}] 发来：{user_msg}")

        # 判断是否是重置指令
        if user_msg in ["重置"]:
            sessions[to_user] = []
            rounds[to_user] = 0
            reply_text = "对话历史已清空，我们可以重新开始了！"
            print(f"[{to_user}]重置对话，轮次已清零")
        else:

            if rounds[to_user] > 20:
                # 已完成用户，不再调用 GPT
                reply_text = "您已完成对话，咨询师已离开"
                print(f"[{to_user}] 已完成，停止对话")
            else:
                
                sessions[to_user].append({"role": "user", "content": user_msg})

                try:
                    input_text = f"【现在是你和用户第 {rounds[to_user]} 轮对话,聊天记录如下】\n\n" + \
                        "\n".join([item['content'] for item in sessions[to_user] if item['role'] == 'user'])

                    if rounds[to_user] == 20:
                        input_text += "\n\n【提示】这是用户的最后一轮咨询，请你用温暖而简短的方式告知并结束本次对话。"

                    response = client.responses.create(
                        model="gpt-4o",
                        instructions=instructions,
                        input=input_text,
                        temperature=1,
                        max_output_tokens=200,
                        truncation="auto"
                    )

                    reply_text = response.output_text.strip()

                    # 判断是否满 20 轮
                    if rounds[to_user] == 20:
                        import random
                        code = str(random.randint(1000, 9999))
                        verify_codes[to_user] = code
                        completed_users.add(to_user)
                        reply_text += f"\n\n您已完成20轮对话，您的验证码是：{code}"
                        print(f"[{to_user}] 触发完成：验证码 {code}")

                    # 保存日志
                    duration = round(time.time() - start, 2)
                    save_response_to_csv(to_user, response, user_msg, rounds[to_user], duration)

                    # 加入 assistant 回复
                    sessions[to_user].append({"role": "assistant", "content": reply_text})

                    print("="*50)
                    print(f"第 {rounds[to_user]} 轮 | 来自 {to_user}")
                    print(f"用户发来：{user_msg}")
                    print(f"ChatGPT回复：{reply_text}")
                    print("="*50)

                    # 调试
                    import pprint
                    pprint.pprint(sessions[to_user])
                    #print("当前已完成对话的用户列表：", completed_users)
                    #print("用户验证码映射表：", verify_codes)


                except Exception as e:
                    print("调用 GPT 出错：", e)
                    reply_text = "出错啦，我暂时无法回复你的消息。"


        # 构建返回给微信服务器的 XML 格式消息
        reply_xml = f"""
        <xml>
          <ToUserName><![CDATA[{to_user}]]></ToUserName>
          <FromUserName><![CDATA[{from_user}]]></FromUserName>
          <CreateTime>{int(time.time())}</CreateTime>
          <MsgType><![CDATA[text]]></MsgType>
          <Content><![CDATA[{reply_text}]]></Content>
        </xml>
        """
        response = make_response(reply_xml)
        response.content_type = 'application/xml'
        return response
    

# 扁平化嵌套字典为键.键.键...  
def flatten_dict(d, parent_key='', sep='.'):
    items = []
    for k, v in d.items():
        new_key = f"{parent_key}{sep}{k}" if parent_key else k
        if isinstance(v, dict):
            items.extend(flatten_dict(v, new_key, sep=sep).items())
        elif isinstance(v, list):
            if all(isinstance(i, dict) for i in v):
                for idx, item in enumerate(v):
                    items.extend(flatten_dict(item, f"{new_key}[{idx}]", sep=sep).items())
            else:
                items.append((new_key, json.dumps(v, ensure_ascii=False)))
        else:
            items.append((new_key, v))
    return dict(items)

def save_response_to_csv(to_user, response, user_msg, round_count, response_time):
    log_dir = "chat_logs"
    os.makedirs(log_dir, exist_ok=True)
    csv_path = os.path.join(log_dir, f"{to_user}_flat.csv")

    # 扁平化 response 字段
    flat = flatten_dict(response.model_dump())

    # 添加基础字段
    flat["__record_time__"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    flat["user_msg"] = user_msg
    flat["round"] = round_count
    flat["response_time"] = response_time

    # ✅ 添加验证码字段
    flat["verify_code"] = verify_codes.get(to_user, "")

    # 写入 CSV
    file_exists = os.path.isfile(csv_path)
    with open(csv_path, 'a', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=flat.keys())
        if not file_exists:
            writer.writeheader()
        writer.writerow(flat)



if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8000)

