import os
import json
import requests
from flask import Flask, request, jsonify, render_template
from dotenv import load_dotenv
from openai import AzureOpenAI

load_dotenv()
app = Flask(__name__)

# Tạo Azure OpenAI client
client = AzureOpenAI(
    api_version=os.getenv("AZURE_API_VERSION"),
    azure_endpoint=os.getenv("AZURE_OPENAI_ENDPOINT"),
    api_key=os.getenv("AZURE_OPENAI_API_KEY"),
)

deployment = os.getenv("AZURE_DEPLOYMENT_NAME")
OWM_API_KEY = os.getenv("OWM_API_KEY")

# Lưu lịch sử hội thoại (global list)
message_history = [
    {"role": "system", "content": "Bạn là một chatbot dự báo thời tiết các tỉnh thành Việt Nam. Trả lời ngắn gọn."}
]

# Hàm thêm vào lịch sử
def add_history(user_msg, ai_response):
    message_history.append({"role": "user", "content": user_msg})
    message_history.append({"role": "assistant", "content": ai_response})

# Hàm lấy thời tiết
def get_weather(city):
    url = f"https://api.openweathermap.org/data/2.5/weather?q={city},VN&appid={OWM_API_KEY}&units=metric&lang=vi"
    r = requests.get(url)
    if r.status_code == 200:
        data = r.json()
        return {
            "city": city,
            "temp": data["main"]["temp"],
            "description": data["weather"][0]["description"]
        }
    return {"error": "Không tìm thấy thành phố."}

# Định nghĩa function để GPT gọi
functions = [
    {
        "name": "get_weather",
        "description": "Lấy thông tin thời tiết tại một tỉnh/thành phố ở Việt Nam",
        "parameters": {
            "type": "object",
            "properties": {
                "city": {"type": "string", "description": "Tên tỉnh hoặc thành phố, ví dụ 'Đà Nẵng'"}
            },
            "required": ["city"]
        }
    }
]

# Prompt gợi ý để GPT học theo
FEW_SHOT_EXAMPLES = [
    {"role": "user", "content": "Thời tiết ở Đà Nẵng hôm nay thế nào?"},
    {"role": "assistant", "content": None, "function_call": {"name": "get_weather", "arguments": '{"city": "Đà Nẵng"}'}},

    {"role": "user", "content": "Cho tôi biết thời tiết Tam Kỳ"},
    {"role": "assistant", "content": None, "function_call": {"name": "get_weather", "arguments": '{"city": "Tam Kỳ"}'}}
]

@app.route("/", methods=["GET"])
def index():
    return render_template("index.html")

@app.route("/chat", methods=["POST"])
def chat():
    print("before: ", message_history)
    user_input = request.json.get("message")

    messages = [
        *FEW_SHOT_EXAMPLES,
        *message_history,
        {"role": "user", "content": user_input}
    ]

    response = client.chat.completions.create(
        model=deployment,
        messages=messages,
        functions=functions,
        function_call="auto"
    )

    msg = response.choices[0].message

    # Nếu GPT gọi function
    if msg.function_call:
        func_name = msg.function_call.name
        args = json.loads(msg.function_call.arguments)

        if func_name == "get_weather":
            result = get_weather(args["city"])

            # Gửi kết quả hàm cho GPT
            messages.append(msg.model_dump())
            messages.append({
                "role": "function",
                "name": func_name,
                "content": json.dumps(result)
            })

            final = client.chat.completions.create(
                model=deployment,
                messages=messages
            )

            ai_reply = final.choices[0].message.content
            add_history(user_input, ai_reply)
            print("after: ", message_history)
            return jsonify({"reply": ai_reply})

    else:
        ai_reply = msg.content
        add_history(user_input, ai_reply)
        print("after: ", message_history)
        return jsonify({"reply": ai_reply})

if __name__ == "__main__":
    import webbrowser
    from threading import Timer

    def open_browser():
        webbrowser.open("http://127.0.0.1:5000")

    if os.environ.get("WERKZEUG_RUN_MAIN") == "true":
        Timer(2.0, open_browser).start()

    if os.getenv("IS_PRODUCTION_MODE", "").strip().lower() == "true":
        app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
    else:
        app.run(debug=True)
