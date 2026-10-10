from PIL import Image, ImageDraw, ImageFont

size = 256   # 图标尺寸
img = Image.new('RGBA', (size, size), (0, 0, 0, 0))
draw = ImageDraw.Draw(img)

# 蓝色圆形
margin = 4
draw.ellipse([margin, margin, size - margin, size - margin],
             fill=(0, 120, 215))

# 绘制白色文字 "JYJX"
text = "JYJX"
try:
    font = ImageFont.truetype("arial.ttf", int(size * 0.35))  # 字号调小以适应4个字母
except IOError:
    font = ImageFont.load_default()

# 让文字水平垂直居中
bbox = draw.textbbox((0, 0), text, font=font)
w = bbox[2] - bbox[0]
h = bbox[3] - bbox[1]
x = (size - w) / 2 - bbox[0]
y = (size - h) / 2 - bbox[1]
draw.text((x, y), text, fill="white", font=font)

# 保存 .ico
img.save("app_icon.ico", format="ICO", sizes=[(size, size)])
print("✅ 图标已生成：app_icon.ico")