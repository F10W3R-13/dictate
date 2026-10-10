"""앱 아이콘 한 벌: 둥근 네모 + 마이크. 트레이(상태별 색)·exe·창 파일이 모두 이걸로 만든다.
`python icon.py` → icon.ico, web/favicon.ico 생성 (색은 앱 강조색).
"""
from PIL import Image, ImageDraw

ACCENT = "#0f766e"


def draw(color=ACCENT, size=256):
    s = 4  # 4배로 그린 뒤 줄여서 가장자리를 부드럽게
    n = size * s
    img = Image.new("RGBA", (n, n))
    d = ImageDraw.Draw(img)
    u = n / 100
    d.rounded_rectangle((0, 0, n - 1, n - 1), radius=22 * u, fill=color)
    w = "white"
    d.rounded_rectangle((38 * u, 17 * u, 62 * u, 55 * u), radius=12 * u, fill=w)  # 마이크 몸통
    d.arc((28 * u, 32 * u, 72 * u, 70 * u), 0, 180, fill=w, width=int(5 * u))  # 받침 호
    d.line((50 * u, 70 * u, 50 * u, 82 * u), fill=w, width=int(5 * u))
    d.line((40 * u, 82 * u, 60 * u, 82 * u), fill=w, width=int(5 * u))
    return img.resize((size, size), Image.LANCZOS)


if __name__ == "__main__":
    big = draw()
    sizes = [(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]
    big.save("icon.ico", sizes=sizes)
    big.save("web/favicon.ico", sizes=sizes[:4])
