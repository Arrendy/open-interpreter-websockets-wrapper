import os
import json
import base64
import traceback
import interpreter
from datetime import datetime
from .websocket_service import send_websocket_message


async def stream_open_interpreter(websocket):
    language = "english"

    try:
        # retain memory of the day
        interpreter.conversation_filename = f"{datetime.now().strftime('%Y%m%d')}.json"
        interpreter.conversation_history_path = "./conversation_histories/"
        if os.path.exists(interpreter.conversation_history_path + interpreter.conversation_filename):
            # If there is, load it and set it as a memory.
            with open(interpreter.conversation_history_path + interpreter.conversation_filename, "r") as f:
                interpreter.messages = json.load(f)
            print("Loaded conversation history.")
        else:
            # Create it if it doesn't exist
            with open(interpreter.conversation_history_path + interpreter.conversation_filename, "w") as f:
                json.dump([], f)
            print("Created conversation history.")

        interpreter.auto_run = True
        # interpreter.debug_mode = True
        interpreter.system_message += f"""
You can use the following libraries without installing:
- pandas
- numpy
- matplotlib
- seaborn
- scikit-learn
- pandas-datareader
- mplfinance
- yfinance
- requests
- scrapy
- beautifulsoup4
- opencv-python
- ffmpeg-python
- PyMuPDF
- pytube
- pyocr
- easyocr
- pydub
- pdfkit
- weasyprint
Your workspace is `./workspace` folder. If you make an output file, please put it in `./workspace/output`.
        """

        message = ""
        saved_file = ""
        prev_type = ""

        while True:
            if message != "" and message != "\n":
                await send_websocket_message(websocket, message, prev_type)

            message = ""
            prev_type = ""

            # Waiting to receive messages via WebSocket
            print("Waiting for user message...")
            user_message = await websocket.receive_text()
            print(f"Received user message: {user_message}")

            parsed_data = json.loads(user_message)
            message_content = parsed_data.get("content")
            message_type = parsed_data.get("type")

            # If you receive a text message on WebSocket
            # ex. {"type": "chat", "content": "Hello"}
            if message_type == "chat" and message_content != "":
                if saved_file != "":
                    user_message = saved_file + user_message
                    saved_file = ""

                # Obtain OpenInterpreter results in stream mode and process each chunk
                is_source_code = False
                for chunk in interpreter.chat(message_content, display=True, stream=True):
                    current_type = list(chunk.keys())[0]
                    exclude_types = ["language", "active_line", "end_of_execution",
                                     "start_of_message", "end_of_message", "start_of_code", "end_of_code"]
                    if current_type not in exclude_types:
                        # For message type, send the message by dividing it into clauses.
                        if current_type != prev_type or (len(message) > 15 and message[-1] in ['、', '。', '！', '？', '；', '…', '：'] or message[-1] == "\n"):
                            if message != "":
                                if "```" in message:
                                    # Toggle is_source_code
                                    is_source_code = not is_source_code
                                else:
                                    type_ = "code" if is_source_code else prev_type
                                    await send_websocket_message(websocket, message, type_)
                            message = ""

                        if current_type == "executing":
                            message += f"{chunk['executing']['code']}\n\n========================\nrunning...\n========================"
                        else:
                            message += chunk[current_type]
                        prev_type = current_type

            # If you receive a file via WebSocket
            # ex. {"type": "file", "fileName": "sample.txt", "fileData": "data:;base64,SGVsbG8sIHdvcmxkIQ=="}
            elif message_type == "file":
                # Parse JSON data to get file name and file data
                file_name = parsed_data.get("fileName")
                base64_data = parsed_data.get("fileData").split(",")[1]
                file_data = base64.b64decode(base64_data)

                # Specify the directory to save the file
                directory = "./workspace"

                # Create the directory if it does not exist
                if not os.path.exists(directory):
                    os.makedirs(directory)

                # Create full path to file
                file_path = os.path.join(directory, file_name)

                # save file
                with open(file_path, "wb") as f:
                    f.write(file_data)

                # add message
                saved_file = f"Saved file to {directory}/{file_name}."
                save_message = "Saved file."
                await send_websocket_message(websocket, save_message, "assistant")

            # If you receive an unconfigured message on WebSocket
            else:
                error_message = "An invalid message was sent."
                await send_websocket_message(websocket, error_message, "assistant")

    except Exception as e:
        print("Errors:", e)
        traceback.print_exc()

        await websocket.close()
