"""偵測 LINE 視窗位置和大小"""
import pyautogui
import time

print("=" * 50)
print("LINE 視窗偵測工具")
print("請確保 LINE 視窗已開啟且未最小化")
print("=" * 50)
print()
print(f"螢幕解析度: {pyautogui.size()}")
print()

# 找所有視窗（需要 pygetwindow）
try:
    import pygetwindow as gw
    
    line_windows = [w for w in gw.getAllWindows() if 'LINE' in w.title.upper()]
    
    if line_windows:
        for i, w in enumerate(line_windows):
            print(f"[{i}] {w.title}")
            print(f"    位置: left={w.left}, top={w.top}")
            print(f"    大小: width={w.width}, height={w.height}")
            print(f"    啟用: {w.isActive}")
            print(f"    可見: {w.isVisible}")
            print(f"    最小化: {w.isMinimized}")
            print()
        
        # 取第一個非最小化的
        active = [w for w in line_windows if not w.isMinimized and w.isVisible]
        if active:
            w = active[0]
            print(f"將使用視窗: {w.title}")
            print(f"座標: ({w.left}, {w.top}) ~ ({w.left + w.width}, {w.top + w.height})")
            print(f"中心點: ({w.left + w.width//2}, {w.top + w.height//2})")
            
            # 啟動視窗
            w.activate()
            time.sleep(0.5)
            
            # 截圖
            screenshot = pyautogui.screenshot(region=(w.left, w.top, w.width, w.height))
            screenshot.save('/mnt/d/我的知識庫/anytocopy-clone/line_window.png')
            print("\n✅ LINE 視窗截圖已儲存: line_window.png")
        else:
            print("❌ 找不到可見的 LINE 視窗")
    else:
        print("❌ 找不到 LINE 視窗")
        print("所有視窗:", [w.title for w in gw.getAllWindows() if w.title])
except ImportError:
    print("⚠️ pygetwindow 未安裝，使用替代方案")
    
    # 簡單螢幕截圖，標示滑鼠位置
    print("請將滑鼠移到 LINE 視窗的左上角，5秒後會偵測位置...")
    print()
    for i in range(5, 0, -1):
        print(f"{i}...")
        time.sleep(1)
    
    pos1 = pyautogui.position()
    print(f"\n左上角位置: {pos1}")
    
    print("現在將滑鼠移到 LINE 視窗的右下角，5秒後偵測...")
    for i in range(5, 0, -1):
        print(f"{i}...")
        time.sleep(1)
    
    pos2 = pyautogui.position()
    print(f"右下角位置: {pos2}")
    
    width = pos2.x - pos1.x
    height = pos2.y - pos1.y
    print(f"推測大小: {width} x {height}")
    
    screenshot = pyautogui.screenshot(region=(pos1.x, pos1.y, width, height))
    screenshot.save('/mnt/d/我的知識庫/anytocopy-clone/line_window.png')
    print("\n✅ LINE 視窗截圖已儲存: line_window.png")

print()
print("現在來拍一張全螢幕確認位置...")
full = pyautogui.screenshot()
full.save('/mnt/d/我的知識庫/anytocopy-clone/full_screen.png')
print("✅ 全螢幕截圖: full_screen.png")
