import sqlite3
import requests
import os
import sys
import time

# --- 定数 ---
DB_PATH = "/home/muo/workspace/summer-28/remo.db"
API_BASE_URL = "https://api.nature.global"
TEMP_RANGE_LOW = 27.0
TEMP_RANGE_HIGH = 29.0
TEMP_CONF_LOW = "28"
TEMP_CONF_HIGH = "30"

# --- データベース関連 ---
def setup_database():
    """データベースとテーブルを初期化する"""
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        # key-valueストアとしてシンプルなテーブルを作成
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS config (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
        ''')
        conn.commit()

def get_config(key):
    """設定値を取得する"""
    # DBがなければ初期化
    if not os.path.exists(DB_PATH):
        setup_database()
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT value FROM config WHERE key = ?", (key,))
        result = cursor.fetchone()
        return result[0] if result else None

def set_config(key, value):
    """設定値を保存する"""
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("INSERT OR REPLACE INTO config (key, value) VALUES (?, ?)", (key, value))
        conn.commit()

# --- API関連 ---
def get_appliances(token):
    """エアコンの一覧を取得する"""
    headers = {"Authorization": f"Bearer {token}"}
    response = requests.get(f"{API_BASE_URL}/1/appliances", headers=headers)
    response.raise_for_status()
    return response.json()

def post_aircon_settings(token, appliance_id, temperature):
    """エアコンの設定を更新する"""
    headers = {"Authorization": f"Bearer {token}"}
    data = {"temperature": str(temperature)}
    response = requests.post(f"{API_BASE_URL}/1/appliances/{appliance_id}/aircon_settings", headers=headers, data=data)
    response.raise_for_status()
    return response.json()

def get_devices(token):
    """デバイスの一覧を取得する"""
    headers = {"Authorization": f"Bearer {token}"}
    response = requests.get(f"{API_BASE_URL}/1/devices", headers=headers)
    response.raise_for_status()
    return response.json()

# --- フロー制御 ---
def setup_flow():
    """対話形式で初期設定を行う"""
    # 1. トークン設定
    print("Nature Remo Cloud APIのアクセストークンが必要です。")
    print("取得先: https://home.nature.global/")
    try:
        token = input("アクセストークンを入力してください: ").strip()
        if not token:
            print("エラー: トークンが入力されませんでした。")
            sys.exit(1)
        set_config("token", token)
        print("トークンを保存しました。")
    except EOFError:
        print("\n入力がキャンセルされました。")
        sys.exit(1)


    # 2. エアコン選択
    try:
        all_appliances = get_appliances(token)
        ac_appliances = [app for app in all_appliances if app['type'] == 'AC']

        if not ac_appliances:
            print("エラー: 操作可能なエアコンが見つかりませんでした。")
            # 不正なトークン等の可能性もあるため、保存したトークンを削除
            set_config("token", "")
            sys.exit(1)

        print("\n制御するエアコンを選択してください:")
        for i, app in enumerate(ac_appliances):
            print(f"[{i}] {app['nickname']}")

        while True:
            try:
                choice_str = input("番号を入力してください: ")
                choice = int(choice_str)
                if 0 <= choice < len(ac_appliances):
                    selected_app = ac_appliances[choice]
                    set_config("appliance_id", selected_app['id'])
                    print(f"「{selected_app['nickname']}」を選択しました。")
                    break
                else:
                    print("無効な番号です。")
            except ValueError:
                print("数値を入力してください。")
            except EOFError:
                print("\n入力がキャンセルされました。")
                sys.exit(1)

    except requests.exceptions.HTTPError as e:
        print(f"APIエラー: {e.response.status_code} {e.response.reason}")
        print("トークンが正しいか、ネットワーク接続を確認してください。")
        # エラーが発生したら保存したトークンを削除してやり直せるようにする
        set_config("token", "")
        sys.exit(1)
    except requests.exceptions.RequestException as e:
        print(f"APIリクエスト中にエラーが発生しました: {e}")
        set_config("token", "")
        sys.exit(1)


def main():
    """メイン処理"""
    # 設定が完了しているかチェック
    token = get_config("token")
    appliance_id = get_config("appliance_id")

    if not token or not appliance_id:
        print("--- 初期設定を開始します ---")
        setup_flow()
        print("\n--- 初期設定が完了しました ---")
        print("再度プログラムを実行して、エアコンの制御を開始してください。")
        sys.exit(0)

    # --- クールダウン判定 ---
    last_set_temp = get_config("last_set_temp")
    last_set_timestamp = get_config("last_set_timestamp")
    if last_set_timestamp:
        elapsed_time = time.time() - float(last_set_timestamp)
        # エアコンOFFを検出した場合のクールダウン（10分）
        if last_set_temp == 'off_detected' and elapsed_time < 600:
            # print(f"エアコンOFF検出後のクールダウン中です。残り{600 - elapsed_time:.0f}秒")
            sys.exit(0)
        # 通常の温度変更後のクールダウン（5分）
        elif last_set_temp != 'off_detected' and elapsed_time < 300:
            # print(f"温度変更後のクールダウン中です。残り{300 - elapsed_time:.0f}秒")
            sys.exit(0)

    # --- キャッシュ優先ロジック ---
    LOGFILE = '/home/muo/templog.txt'
    try:
        if os.path.exists(LOGFILE) and (time.time() - os.path.getmtime(LOGFILE)) < 120: # 2分以内
            with open(LOGFILE, 'r') as f:
                lines = f.readlines()
                if lines:
                    last_line = lines[-1].strip()
                    # タブで分割し、最後の要素を温度として取得
                    temp_str = last_line.split('\t')[-1]
                    cached_temp = float(temp_str)
                    if TEMP_RANGE_LOW < cached_temp <= TEMP_RANGE_HIGH:
                        # print(f"キャッシュされた室温 ({cached_temp}°C) は適温範囲内です。APIアクセスは行わず、処理を終了します。")
                        sys.exit(0)
    except (IOError, ValueError, IndexError) as e:
        print(f"キャッシュファイルの読み込み/パースエラー (API処理に移行します): {e}")
    # --- キャッシュ優先ロジックここまで ---


    # --- 通常の制御モード (APIアクセス実行) ---
    print("--- エアコン制御バッチ実行 (APIアクセスあり) ---")
    try:
        # 1. エアコンの情報を取得
        appliances = get_appliances(token)
        target_appliance = next((app for app in appliances if app['id'] == appliance_id), None)

        if not target_appliance:
            print(f"エラー: 設定されたエアコン(ID: {appliance_id})が見つかりません。")
            print("設定をリセットします。もう一度実行して再設定してください。")
            set_config("appliance_id", "")
            sys.exit(1)

        # 2. エアコンに紐づくデバイスのIDを取得
        device_id = target_appliance.get('device', {}).get('id')
        if not device_id:
            print("エラー: エアコンに紐づくデバイスIDが見つかりません。")
            sys.exit(1)

        # 3. 全デバイスの最新情報を取得
        devices = get_devices(token)
        target_device = next((dev for dev in devices if dev['id'] == device_id), None)

        if not target_device:
            print(f"エラー: デバイス(ID: {device_id})の情報が見つかりません。")
            sys.exit(1)

        # 4. デバイス情報から室温を取得
        current_temp = target_device.get('newest_events', {}).get('te', {}).get('val')
        if current_temp is None:
            print("エラー: 現在の室温を取得できませんでした。'/1/devices' の応答に温度情報が含まれていません。")
            sys.exit(1)

        # 5. エアコン情報から現在の設定と電源状態を取得
        settings = target_appliance.get('settings', {})
        print(settings)
        current_set_temp = settings.get('temp', '')
        # buttonが''（空文字列）の場合は電源ON, 'power-off'の場合は電源OFF
        power_status = 'on' if settings.get('button', '') in ('', 'power-on') else 'off'

        print(f"エアコン: {target_appliance['nickname']}")
        print(f"現在の室温: {current_temp}°C")
        print(f"現在の設定温度: {current_set_temp}°C")
        print(f"電源状態: {power_status}")

        # 6. 電源がOFFの場合の処理
        if power_status == 'off':
            print("エアコンの電源がOFFのため、温度変更は行いません。")
            # 温度が範囲外の場合、次回実行を10分遅らせる
            if current_temp > TEMP_RANGE_HIGH or current_temp <= TEMP_RANGE_LOW:
                print("室温が範囲外のため、10分間のクールダウンを設定します。")
                set_config("last_set_temp", "off_detected")
                set_config("last_set_timestamp", str(time.time()))
            sys.exit(0)

        # 7. (電源ONの場合の)制御ロジック
        if current_temp > TEMP_RANGE_HIGH:
            if current_set_temp != TEMP_CONF_LOW:
                print(f"室温が{TEMP_RANGE_HIGH}°Cを超えたため、設定温度を{TEMP_CONF_LOW}°Cに変更します...")
                post_aircon_settings(token, appliance_id, TEMP_CONF_LOW)
                set_config("last_set_temp", TEMP_CONF_LOW)
                set_config("last_set_timestamp", str(time.time()))
                print("変更しました。")
            else:
                print(f"設定温度は既に{TEMP_CONF_LOW}°Cのため、操作は行いません。")
        elif current_temp <= TEMP_RANGE_LOW:
            if current_set_temp != TEMP_CONF_HIGH:
                print(f"室温が{TEMP_RANGE_LOW}°C以下になったため、設定温度を{TEMP_CONF_HIGH}°Cに変更します...")
                post_aircon_settings(token, appliance_id, TEMP_CONF_HIGH)
                set_config("last_set_temp", TEMP_CONF_HIGH)
                set_config("last_set_timestamp", str(time.time()))
                print("変更しました。")
            else:
                print(f"設定温度は既に{TEMP_CONF_HIGH}°Cのため、操作は行いません。")
        else:
            print(f"室温は適正範囲内（{TEMP_RANGE_LOW}°C < T <= {TEMP_RANGE_HIGH}°C）です。")

    except requests.exceptions.HTTPError as e:
        print(f"APIエラー: {e.response.status_code} {e.response.reason}")
        if e.response.status_code == 401:
            print("認証エラーです。トークンが無効になっている可能性があります。")
            print("設定をリセットします。もう一度実行して再設定してください。")
            set_config("token", "")
            set_config("appliance_id", "")
        sys.exit(1)
    except requests.exceptions.RequestException as e:
        print(f"APIリクエスト中にエラーが発生しました: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"予期せぬエラーが発生しました: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
