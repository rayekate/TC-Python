import requests, getpass

BASE = "http://localhost:8000"
S = requests.Session()  # keeps cookies

# A) Send code
# phone = input("Phone (+91...): ").strip()
phone = "+917903299241"
r = S.post(f"{BASE}/auth/phone/start", json={"phoneNumber": phone})
print("START:", r.status_code, r.text)
r.raise_for_status()

# B) Verify OTP
otp = input("Enter 5-digit OTP: ").strip()
r = S.post(f"{BASE}/auth/phone/verify", json={"code": otp})
print("VERIFY:", r.status_code, r.text)

if r.ok:
    j = r.json()
    if j.get("needsPassword"):
        pwd = getpass.getpass("Enter Telegram cloud password: ")
        r = S.post(f"{BASE}/auth/phone/password", json={"password": pwd})
        print("PASSWORD:", r.status_code, r.text)
