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
import logging
import random

# 隐藏 Flask 的访问请求日志
log = logging.getLogger('werkzeug')
log.setLevel(logging.ERROR)

sessions = defaultdict(list)
rounds = defaultdict(int)
completed_users = set()
verify_codes = {}

client = OpenAI()

with open("prompt_example.txt", "r", encoding="utf-8") as f:
    system_prompt = f.read()

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
      
        if hashcode == signature:
            return echostr
        else:
            return '验证失败'

    elif request.method == 'POST':
        start = time.time()

        xml_data = request.data
        root = ET.fromstring(xml_data)
        user_msg = root.find('Content').text.strip()
        to_user = root.find('FromUserName').text
        from_user = root.find('ToUserName').text
        
        rounds[to_user] += 1
        print(f"第 {rounds[to_user]} 轮 | 来自 {to_user}")
        print(f"用户发来：{user_msg}")

        if user_msg == "重置":
            sessions[to_user] = []
            rounds[to_user] = 0
            completed_users.discard(to_user)
            verify_codes.pop(to_user, None)
            reply_text = "对话历史已清空，我们可以重新开始了！"

        elif to_user in completed_users:
            reply_text = "您已完成对话，咨询师已离开"
        else:
            # 正常对话流程
            sessions[to_user].append({"role": "user", "content": user_msg})

            try:
                messages = [{"role": "system", "content": system_prompt}]
                messages.extend(sessions[to_user])

                if rounds[to_user] == 10:
                    messages.append({"role": "system", "content": "请注意，这将是用户的最后一轮对话，请你用温暖的语言结束咨询。"})

                response = client.chat.completions.create(
                    model="gpt-4.1-nano",
                    messages=messages,
                    temperature=1,
                    max_tokens=200
                )

                reply_text = response.choices[0].message.content.strip()

                if rounds[to_user] == 10:
                    code = str(random.randint(1000, 9999))
                    verify_codes[to_user] = code
                    completed_users.add(to_user)
                    reply_text += f"\n\n您已完成10轮对话，您的验证码是：{code}"

                sessions[to_user].append({"role": "assistant", "content": reply_text})

                duration = round(time.time() - start, 2)
                save_chat_response_to_csv(to_user, response, user_msg, rounds[to_user], duration, verify_codes.get(to_user))

                print("="*50)
                print(f"ChatGPT回复：{reply_text}")
                print("="*50)

                # 调试
                #import pprint
                #pprint.pprint(sessions[to_user])
                #print("当前已完成对话的用户列表：", completed_users)
                #print("用户验证码映射表：", verify_codes)

            except Exception as e:
                print("调用 GPT 出错：", e)
                reply_text = "咨询师不在线哦"

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

def save_chat_response_to_csv(to_user, response, user_msg, round_count, response_time, verify_code=None):
    # 保存完整的响应内容为 JSON 文件（调试用）
    debug_log_path = os.path.join("chat_logs", f"{to_user}_raw_response.json")
    with open(debug_log_path, 'w', encoding='utf-8') as f:
        json.dump(response.model_dump(), f, ensure_ascii=False, indent=2)

    log_dir = "chat_logs"
    os.makedirs(log_dir, exist_ok=True)
    csv_path = os.path.join(log_dir, f"{to_user}_chat.csv")

    flat = {
        "__record_time__": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "user_msg": user_msg,
        "round": round_count,
        "response_time": response_time,
        "verify_code": verify_code or "",
        "model": response.model,
        "reply_text": response.choices[0].message.content.strip(),
        "finish_reason": response.choices[0].finish_reason,
        "prompt_tokens": response.usage.prompt_tokens,
        "completion_tokens": response.usage.completion_tokens,
        "total_tokens": response.usage.total_tokens,
        "cached_tokens": response.usage.prompt_tokens_details.cached_tokens,
        "reasoning_tokens": response.usage.completion_tokens_details.reasoning_tokens,
        "service_tier": response.service_tier,
        "system_fingerprint": response.system_fingerprint,
        "created_unix": response.created
    }
    
    file_exists = os.path.isfile(csv_path)
    with open(csv_path, 'a', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=flat.keys())
        if not file_exists:
            writer.writeheader()
        writer.writerow(flat)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8000)
