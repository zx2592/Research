# V2.2: Mac 鏃犲ご鏈嶅姟鍣ㄩ儴缃蹭笌 Agent 寮哄寲鏀归€犺鍒?

> **鏇存柊鐩爣**: 灏嗗綋鍓嶅熀浜?Windows + IDE AI 寮轰緷璧栫殑鐮旂┒绯荤粺锛屽崌绾т负鍙湪 Mac (鍙婂叾浠?Unix-like) 鏈嶅姟鍣ㄤ笂鐙珛杩愯鐨勩€佸叿澶囩函鏈湴鍐呯疆 Agent 鑳藉姏鐨勬棤澶?(Headless) 鏈嶅姟绔郴缁熴€?

## 1. 鏍稿績鏋舵瀯璋冩暣鐞嗗康 (鏂规 A)

涓轰簡瀹炵幇鍦?Mac 涓婇€氳繃 Telegram锛圛M锛夊彂鍑烘寚浠わ紝骞跺緱鍒扮瓑鏁堜簬 IDE 鍐呯疆 AI锛堝 Antigravity / Cursor锛夋繁搴︾爺绌剁粨鏋滅殑鐩爣锛?*鎴戜滑涓嶅皾璇曢€氳繃澶栭儴鑴氭湰鍞ら啋 IDE 鎻掍欢**锛堟妧鏈笂鏋侀毦瀹炵幇涓斾笉绋冲畾锛夛紝鑰屾槸**澧炲己鍐呯疆鐨?`core/llm_client.py`**锛岃祴浜堝叾绛夊悓浜?IDE 鎻掍欢鐨勮兘鍔涳細

*   **褰撳墠 IDE AI 涓轰粈涔堣仾鏄庯紵** = `澶фā鍨媊 + `IDE鎻愪緵鐨勫伐鍏?(Tools)` + `.agent/workflows/ 涓嬬殑楂橀樁鎻愮ず璇峘銆?
*   **V2.2 寮哄寲鐗堝悗鍙?Agent** = `鐩稿悓鐨?Gemini 妯″瀷` + `閲嶅啓鐨?Python 鏈湴宸ュ叿鍑芥暟` + `璇诲彇鍚屾牱鐨?workflows 鏂囦欢浣滀负 Prompt`銆?

杩欐牱锛屽嵆浣?Mac 澶勪簬鈥滃悎鐩栧緟鏈衡€濇垨娌℃湁浠讳綍 IDE 鎵撳紑鐨勭姸鎬侊紝Telegram Bot 瑙﹀彂鐨勭嫭绔?Python 杩涚▼涔熻兘鑷富鏀堕泦鏁版嵁銆佹€濊€冦€佹悳绱㈠苟鐢熸垚楂樿川閲忔姤鍛娿€?

---

## 2. 浠ｇ爜绾у叿浣撴敼閫犳楠?(To-Do List)

### 2.1 澧炲己 Agent 宸ュ叿绠?(Tools)
鍦?`research_cli.py` (鎴栨彁鍙栬嚦涓撻棬鐨?`tools.py`) 涓紝闄や簡鐜版湁鐨?`search_web` 鍜?`write_to_file`锛岄渶瑕佽ˉ鍏呬互涓嬫牳蹇?Agent 绾ц兘鍔涳紝骞跺皢瀹冧滑娉ㄥ唽缁?`gemini` 鐨?`ContentConfig(tools=[...])`锛?
*   [ ] `read_file(filepath)`: 璇诲彇鎸囧畾鏈湴鏂囦欢鍐呭锛堝挨涓洪噸瑕侊紝璁?Agent 鑳借嚜鎴戞煡闃呰储鎶?JSON 鍜屼箣鍓嶇敓鎴愮殑鎶ュ憡锛夈€?
*   [ ] `list_dir(path)`: 鍒楀嚭鐩綍鍐呭锛岃 Agent 鎷ユ湁鏂囦欢绯荤粺鎰熺煡鑳藉姏銆?
*   [ ] `run_python(code)` (鍙€?: 鎻愪緵鍙楅檺鐜璁?Agent 鎵ц涓存椂鑴氭湰鎶撳彇鎴栧垎鏋愭暟鎹€?

### 2.2 妗ユ帴 Workflows 涓庡悗鍙?Agent
IDE AI 鐨勭伒榄傚湪浜?`.agent/workflows/` 涓殑浼樿川 Prompt 缂栨帓銆?
*   [ ] 淇敼 `research_cli.py` 鎴?`core/llm_client.py`锛屽湪鍝嶅簲 Telegram 鐨?`/scan`銆乣/deep` 绛夋寚浠ゆ椂锛?*鑷姩璇诲彇瀵瑰簲 `workflows/` 涓嬬殑 `.md` 鏂囦欢鍏ㄦ枃**銆?
*   [ ] 灏嗚鍑虹殑 workflow 鍐呭浣滀负鏈€楂樻潈閲嶇殑 `system_instruction` 浼犻€掔粰澶фā鍨嬶紝纭繚鍏舵€濊€冨拰杈撳嚭鏍煎紡涓?IDE 鐜涓嬪畬鍏ㄤ竴鑷淬€?
*   [ ] 瀵?`/deep` 绛夐渶瑕佹繁搴︽帹鐞嗙殑鎸囦护锛岃嚜鍔ㄥ垏鎹㈡寕杞芥渶楂樻櫤鍔涙ā鍨?(`gemini-3-pro` 鎴?Claude 3.5 Sonnet 绛夋晥妯″瀷)銆?

### 2.3 鏍归櫎 Windows 纭紪鐮佺殑璺ㄥ钩鍙板吋瀹逛慨澶?
鍏ㄥ簱鎵弿娓呯悊渚濊禆 `d:/` 鐨勭粷瀵硅矾寰勶紝鏀逛负鐩稿浜?`PROJECT_ROOT` 鐨勫姩鎬佽矾寰勶細
*   [ ] `test_notification.py`, `test_guba.py`, `test_full_flow.py`, `test_collection.py`锛氭竻鐞?`open('d:/AI/Auto/system/config.yaml')`銆?
*   [ ] `scrapers/report_scraper.py`锛氬皢涓嬭浇璺緞閲嶆瀯涓?`os.path.join(PROJECT_ROOT, "downloads")`銆?

### 2.4 Telegram 鍝嶅簲閫昏緫閲嶆瀯
Agentic Task (甯︽湁杩炵画鍙嶆€濆拰宸ュ叿璋冪敤鐨勪换鍔? 闇€瑕佽緝闀跨殑鏃堕棿锛屽彲鑳界獊鐮存爣鍑?Webhook 鎴栭暱杞鐨勮秴鏃堕檺鍒躲€?
*   [ ] 浼樺寲 `bot/telegram_bot.py` 鐨勫紓姝ョ瓑寰呮満鍒讹紝鍦?Agent 鎵ц澶嶆潅澶氭鎬濊€冩椂锛孊ot 姣忛殧涓€瀹氭椂闂村彂閫佲€滀粛鍦ㄦ繁搴︽€濊€冧腑...(绗?N 姝?鈥濈殑涓棿鐘舵€佸弽棣堢粰鐢ㄦ埛銆?
*   [ ] 寮哄寲 `send_long_message`锛屽簲瀵?Agent 鍙兘杈撳嚭鐨勮秴闀跨爺鎶ャ€?

### 2.5 Mac 闃蹭紤鐪犱笌杩涚▼甯搁┗ (绯荤粺绾ч厤缃?
*   [ ] 缂栧啓 `start_mac.sh` 鍚姩鑴氭湰銆?
*   [ ] 鍦ㄨ剼鏈腑浣跨敤 `caffeinate -i -s python bot/telegram_bot.py` 鎴栨帹鑽愪娇鐢?`pm2` / `launchd` 绛夎繘绋嬩繚娲诲伐鍏凤紝纭繚 Macbook 鍚堢洊鎴栨棤浜哄€煎畧鏃剁綉缁滃拰鏈嶅姟涓嶆柇寮€銆?
*   [ ] 缁撳悎 Tailscale (鎴?ZeroTier) 缁勫缓鍐呴儴灞€鍩熺綉锛屼娇寰楃敤鎴峰湪浠讳綍鍦版柟鐨勪究鎼鸿澶囷紙iPad/杞昏杽鏈級涓婂彧瑕佸畨瑁呬簡 VSCode锛岄兘鑳戒竴閿厤瀵?SSH 杩涘叆 Macbook 缂栬緫鎶ュ憡銆?

---

## 3. 楠屾敹鏍囧噯

瀹屾垚涓婅堪鏀归€犲悗锛屽彲浠ラ€氳繃浠ヤ笅鍦烘櫙杩涜鍔熻兘鎵撴牱涓庨獙鏀讹細
1. **绾悗鍙拌Е鍙?*锛氬湪 Mac 涓婁笉鎵撳紑浠讳綍浠ｇ爜缂栬緫鍣紝鐩存帴浠庢墜鏈?Telegram 鍙戦€?`/scan` 鎴?`/deep NVDA`銆?
2. **瀹屽叏绛夋晥**锛欱ot 缁忚繃鍑犲垎閽熸€濊€冨悗杩斿洖鐨勬姤鍛婃牸寮忥紝涓庡綋鍓嶄娇鐢?IDE Agent 瑙ｆ瀽鐨勫伐浣滄祦鏂囦欢鐢熸垚鐨勬姤鍛婃牸寮忋€佹繁搴︽鏃犱簩鑷淬€?
3. **鏂囦欢钀藉湴**锛氭墍鏈夋姤鍛婅嚜鍔ㄦ寜鏃ユ湡瑙勫垯钀界洏鑷?Mac 鐨?`Reports/` 鐩綍涓嬨€?
