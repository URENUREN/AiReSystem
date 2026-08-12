// ==UserScript==
// @name         AiReLinker All-in-One Hybrid Log Sender (v10.0.1)
// @namespace    https://airesystem.local/
// @version      10.0.1
// @description  Google AI Studio, Gemini, ChatGPT, Google AI Overviews の対話・画像ログを爆速自動収集 ＆ AiReSystemへ直接同期 (検索時AI概要存在時のみ表示修復版)
// @author       AiReSystem
// @match        https://aistudio.google.com/*
// @match        https://gemini.google.com/*
// @match        https://chatgpt.com/*
// @match        https://chat.openai.com/*
// @match        https://www.google.com/search*
// @match        https://www.google.co.jp/search*
// @grant        GM_xmlhttpRequest
// @connect      127.0.0.1
// @connect      localhost
// @connect      google.com
// @connect      googleusercontent.com
// @connect      googleapis.com
// @connect      gstatic.com
// @connect      openai.com
// @connect      oaiusercontent.com
// ==/UserScript==

(function () {
    'use strict';

    // 🌟 現在のWebサービス判定
    const hostname = window.location.hostname;
    const isGeminiWeb = hostname.includes('gemini.google.com');
    const isAIStudio = hostname.includes('aistudio.google.com');
    const isChatGPT = hostname.includes('chatgpt.com') || hostname.includes('openai.com');
    const isAIOverview = hostname.includes('google.') && window.location.pathname.includes('/search');

    let scrollCancelled = false;
    let globalMediaCache = {};
    let globalCollectedTurns = [];
    let capturedTurnSet = new Set();

    // 🌟 サービス別チャットタイトルの自動抽出 (ファイル名安全性クレンジング付き)
    function getChatTitle() {
        let rawTitle = "";

        if (isGeminiWeb) {
            let titleEl = document.querySelector('a[data-test-id="conversation"].selected, .conversation-title');
            rawTitle = titleEl ? titleEl.textContent.trim() : "";
            if (!rawTitle || rawTitle.toLowerCase().includes("gemini")) rawTitle = document.title || "";
            rawTitle = rawTitle.replace(/\s*[-–—]\s*(Google\s*)?Gemini.*$/i, '').replace(/^(Google\s*)?Gemini\s*[-–—]\s*/i, '').replace(/^[✓✔]\s*/, '').trim();
            if (!rawTitle || rawTitle.toLowerCase() === "gemini") rawTitle = "Gemini_Chat_" + new Date().toISOString().slice(11, 19).replace(/:/g, "-");
        } else if (isAIStudio) {
            let titleInput = document.querySelector('input[placeholder="Untitled prompt"], input.prompt-title, .title-input input');
            if (titleInput && titleInput.value.trim() !== "") return titleInput.value.trim();
            rawTitle = (document.title || "").replace(/[\s\-–—_]*Google[\s_]AI[\s_]Studio.*/i, '').trim();
            if (!rawTitle || rawTitle.toLowerCase().includes("untitled prompt")) rawTitle = "Untitled_Chat_" + new Date().toISOString().slice(11, 19).replace(/:/g, "-");
        } else if (isChatGPT) {
            rawTitle = (document.title || "").replace(/\s*[-–—_]\s*ChatGPT.*/i, '').replace(/^ChatGPT\s*[-–—_]\s*/i, '').trim();
            if (!rawTitle || rawTitle.toLowerCase() === "chatgpt") {
                const activeNav = document.querySelector('nav a.bg-token-sidebar-surface-tertiary, nav a[class*="active"]');
                if (activeNav) rawTitle = activeNav.textContent.trim();
            }
            if (!rawTitle || rawTitle.toLowerCase() === "chatgpt") rawTitle = "ChatGPT_Chat_" + new Date().toISOString().slice(11, 19).replace(/:/g, "-");
        } else if (isAIOverview) {
            const urlParams = new URLSearchParams(window.location.search);
            const query = urlParams.get('q');
            if (query) rawTitle = query.trim();
            else {
                const inputEl = document.querySelector('input[name="q"], textarea[name="q"]');
                rawTitle = inputEl ? inputEl.value.trim() : 'AI_Overview';
            }
        }

        return (rawTitle || 'AI_Chat').replace(/[\\/:*?"<>|]/g, '_').replace(/\s+/g, ' ').trim().slice(0, 25);
    }

    // 🌟 サービス名の取得
    function getAIServiceName() {
        if (isGeminiWeb) return "Gemini";
        if (isAIStudio) return "Google AI Studio";
        if (isChatGPT) return "ChatGPT";
        if (isAIOverview) return "AI Overviews";
        return "AI_Service";
    }

    // 🌟 Blob ➔ Base64 変換
    function blobToBase64(blob) {
        return new Promise((resolve, reject) => {
            const reader = new FileReader();
            reader.onloadend = () => {
                if (reader.result) {
                    const mimeMatch = reader.result.match(/^data:(.*?);base64,/);
                    const mimeType = mimeMatch ? mimeMatch[1] : (blob.type || 'image/png');
                    const b64Data = reader.result.replace(/^data:[^;]+;base64,/, '');
                    resolve({ mimeType: mimeType, data: b64Data });
                } else {
                    resolve(null);
                }
            };
            reader.onerror = reject;
            reader.readAsDataURL(blob);
        });
    }

    // 🌟 画像・メディアの Base64 超高速キャプチャ
    function fetchBase64FromUrl(src) {
        if (!src || src.startsWith('data:')) return Promise.resolve(null);

        return new Promise((resolve) => {
            GM_xmlhttpRequest({
                method: "GET",
                url: src,
                responseType: "blob",
                timeout: 4000,
                onload: function (response) {
                    if (response.status === 200 && response.response) {
                        const blob = response.response;
                        if (blob.size > 50 * 1024 * 1024) {
                            resolve({ type: 'large_file', src: src, size: blob.size });
                        } else {
                            blobToBase64(blob).then(resolve).catch(() => resolve(null));
                        }
                    } else {
                        fetch(src).then(r => r.blob()).then(b => blobToBase64(b)).then(resolve).catch(() => resolve(null));
                    }
                },
                onerror: function () {
                    fetch(src).then(r => r.blob()).then(b => blobToBase64(b)).then(resolve).catch(() => resolve(null));
                },
                ontimeout: function () { resolve(null); }
            });
        });
    }

    // 🌟 DOM 階層深層スキャナー (Shadow DOM貫通対応)
    function querySelectorAllDeep(selector, node = document.body, found = []) {
        if (!node) return found;
        if (node.querySelectorAll && node.nodeType === Node.ELEMENT_NODE) {
            const elements = node.querySelectorAll(selector);
            elements.forEach(el => { if (!found.includes(el)) found.push(el); });
        }
        if (node.shadowRoot) querySelectorAllDeep(selector, node.shadowRoot, found);
        let child = node.firstChild;
        while (child) {
            querySelectorAllDeep(selector, child, found);
            child = child.nextSibling;
        }
        return found;
    }

    // 🌟 スクロール可能なメインコンテナの探索
    function findScrollableNode() {
        if (isChatGPT) {
            return document.querySelector('main div.overflow-y-auto') || document.querySelector('main') || window;
        }
        if (isAIOverview) return window;

        function findDeep(node = document.body) {
            if (!node) return null;
            if (node.nodeType === Node.ELEMENT_NODE) {
                const style = window.getComputedStyle(node);
                const isScrollable = (style.overflowY === 'auto' || style.overflowY === 'scroll') && node.scrollHeight > node.clientHeight;
                const tagName = node.tagName.toLowerCase();
                if (tagName.includes('conversation-stream') || tagName.includes('chat-history') || isScrollable) return node;
            }
            if (node.shadowRoot) {
                const found = findDeep(node.shadowRoot);
                if (found) return found;
            }
            let child = node.firstChild;
            while (child) {
                const found = findDeep(child);
                if (found) return found;
                child = child.nextSibling;
            }
            return null;
        }
        return findDeep(document.body) || window;
    }

    // 🌟 メディアアセットの深層抽出
    function findMediaAssetsDeep(node, foundAssets = []) {
        if (!node) return foundAssets;

        if (node.tagName === 'IMG' && node.src) {
            const isAvatar = node.src.includes('avatar') || node.src.includes('profile') || node.src.includes('user') || node.src.includes('googleusercontent.com/a/') || node.src.startsWith('data:image/svg+xml');
            if (!isAvatar) foundAssets.push({ type: 'img', src: node.src, element: node });
        }

        if (node.style && node.style.backgroundImage) {
            const match = node.style.backgroundImage.match(/url\(['"]?(.*?)['"]?\)/);
            if (match && match[1]) foundAssets.push({ type: 'img', src: match[1], element: node });
        }

        if ((node.tagName === 'AUDIO' || node.tagName === 'VIDEO') && node.src) {
            foundAssets.push({ type: node.tagName.toLowerCase(), src: node.src, element: node });
        }

        if (node.shadowRoot) findMediaAssetsDeep(node.shadowRoot, foundAssets);
        let child = node.firstChild;
        while (child) {
            findMediaAssetsDeep(child, foundAssets);
            child = child.nextSibling;
        }
        return foundAssets;
    }

    // 🌟 可視領域の発言ターンのリアルタイムキャプチャ
    async function captureVisibleTurnsOnTheFly() {
        let newCount = 0;

        if (isAIOverview) {
            const aiContainer = document.querySelector('[data-subtree="aimc"]') || document.querySelector('[jsname="V3qe9d"]') || document.querySelector('[data-container-id="main-col"]');
            if (!aiContainer || capturedTurnSet.has(aiContainer)) return { count: 0, hasViewportMedia: false };

            const clone = aiContainer.cloneNode(true);
            clone.querySelectorAll('button, script, style, svg, [role="button"]').forEach(el => el.remove());
            const rawText = (clone.innerText || clone.textContent || '').trim();
            if (!rawText) return { count: 0, hasViewportMedia: false };

            capturedTurnSet.add(aiContainer);
            const query = getChatTitle();
            const mediaElements = findMediaAssetsDeep(aiContainer);

            globalCollectedTurns.push({ role: 'user', parts: [{ text: query }], timestamp: Date.now() });

            const modelParts = [{ text: rawText }];
            for (const media of mediaElements) {
                let inlineData = globalMediaCache[media.src];
                if (!inlineData) {
                    inlineData = await fetchBase64FromUrl(media.src);
                    if (inlineData) globalMediaCache[media.src] = inlineData;
                }
                if (inlineData) modelParts.push({ inlineData: inlineData });
            }

            globalCollectedTurns.push({ role: 'model', parts: modelParts, timestamp: Date.now() });
            return { count: 2, hasViewportMedia: mediaElements.length > 0 };
        }

        const selector = isChatGPT ? 'article, [data-testid^="conversation-turn-"]' : (isGeminiWeb ? 'user-query, model-response' : 'ms-chat-turn');
        const turnElements = querySelectorAllDeep(selector);

        for (const el of turnElements) {
            if (capturedTurnSet.has(el)) continue;

            let isUser = false;
            if (isChatGPT) {
                const authorRoleEl = el.querySelector('[data-message-author-role]');
                const roleAttr = authorRoleEl ? authorRoleEl.getAttribute('data-message-author-role') : '';
                isUser = (roleAttr === 'user' || (el.innerHTML || '').toLowerCase().includes('user-prompt'));
            } else if (isGeminiWeb) {
                isUser = (el.tagName.toLowerCase() === 'user-query' || el.classList.contains('user-query'));
            } else {
                isUser = ((el.outerHTML || '').toLowerCase().includes('user-prompt-container'));
            }

            let rawText = (el.innerText || el.textContent || '').trim();
            const mediaElements = findMediaAssetsDeep(el);

            if (!rawText && mediaElements.length === 0) continue;

            capturedTurnSet.add(el);
            const parts = [];
            if (rawText) parts.push({ text: rawText });

            const uniqueSrcs = Array.from(new Set(mediaElements.map(x => x.src)));
            for (const src of uniqueSrcs) {
                let inlineData = globalMediaCache[src];
                if (!inlineData) {
                    inlineData = await fetchBase64FromUrl(src);
                    if (inlineData) globalMediaCache[src] = inlineData;
                }
                if (inlineData && inlineData.type !== 'large_file') {
                    parts.push({ inlineData: inlineData });
                }
            }

            globalCollectedTurns.push({
                role: isUser ? 'user' : 'model',
                parts: parts,
                timestamp: Date.now()
            });

            newCount++;
        }

        return { count: newCount, hasViewportMedia: false };
    }

    // 🌟 防護シールド overlay 生成ヘルパー
    function getOrCreateShield() {
        let shield = document.getElementById('airelinker-shield-overlay');
        if (!shield) {
            shield = document.createElement('div');
            shield.id = 'airelinker-shield-overlay';
            shield.style.cssText = 'position:fixed; top:0; left:0; width:100vw; height:100vh; background:rgba(0,0,0,0.65); z-index:999990; display:flex; flex-direction:column; justify-content:center; align-items:center; font-family:sans-serif;';
            document.body.appendChild(shield);
        } else {
            shield.innerHTML = '';
            shield.style.display = 'flex';
        }
        return shield;
    }

    function removeShield() {
        const shield = document.getElementById('airelinker-shield-overlay');
        if (shield && shield.parentNode) {
            shield.parentNode.removeChild(shield);
        }
    }

    // 🌟 右下小パネルデザイン (修復: Google検索時AI概要非存在ガード)
    function createPanel() {
        if (document.getElementById('airelinker-panel')) return;

        // 🌟 1. Google 検索画面の場合、AI Overview (AI概要) ブロックが無ければパネルを表示しないガード！
        if (isAIOverview) {
            const aiContainer = document.querySelector('[data-subtree="aimc"]') || document.querySelector('[jsname="V3qe9d"]');
            if (!aiContainer) return; // AI概要が無い場合は何も表示しない！
        }

        const panel = document.createElement('div');
        panel.id = 'airelinker-panel';
        panel.style.cssText = 'position:fixed; bottom:20px; right:20px; z-index:99999; background:#ffffff; border:2px solid #0284c7; border-radius:12px; padding:12px; box-shadow:0 10px 25px rgba(0,0,0,0.15); display:flex; flex-direction:column; gap:8px; width:240px; font-family:sans-serif;';

        const title = document.createElement('div');
        title.innerText = `⚓ AiReLinker (${getAIServiceName()})`;
        title.style.cssText = 'text-align:center; color:#0369a1; font-size:13px; font-weight:bold; margin-bottom:2px;';
        panel.appendChild(title);

        function createBtn(text, bgColor) {
            const b = document.createElement('button');
            b.innerText = text;
            b.style.cssText = `padding:8px 10px; border:none; border-radius:6px; cursor:pointer; font-weight:bold; font-size:11px; color:#ffffff; background-color:${bgColor}; transition:0.2s; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; height:32px; box-sizing:border-box;`;
            return b;
        }

        if (isGeminiWeb || isAIStudio) {
            const btnPreload = createBtn('⚡ 事前ロード高速スクロール', '#10b981');
            btnPreload.onclick = () => fastPreloadScroll(true);

            const btnFull = createBtn('🚀 自動スクロール全取得', '#e67e22');
            btnFull.onclick = () => autoScrollAndSend(btnFull, false);

            const btnAutoAll = createBtn('⚡ 事前ロード ＋ 全取得', '#2563eb');
            btnAutoAll.onclick = () => runFullPreloadAndSend(btnAutoAll);

            panel.appendChild(btnPreload);
            panel.appendChild(btnFull);
            panel.appendChild(btnAutoAll);
        } else {
            const btnFull = createBtn('🚀 爆速全取得 ＆ 送信', '#16a34a');
            btnFull.onclick = () => autoScrollAndSend(btnFull, false);
            panel.appendChild(btnFull);
        }

        document.body.appendChild(panel);
    }

    // 🌟 1. 【高速事前ロード】
    async function fastPreloadScroll(isStandalone = true) {
        scrollCancelled = false;
        const scrollableNode = findScrollableNode();

        let shield = null;
        let statusMsg = null;
        let btnArea = null;

        if (isStandalone) {
            shield = getOrCreateShield();
            statusMsg = document.createElement('div');
            statusMsg.innerText = '⚡ 事前ロード巡回中: 最上部へ移動中...';
            statusMsg.style.cssText = 'color:#fff; font-size:18px; font-weight:bold; margin-bottom:20px; text-shadow:0 2px 4px rgba(0,0,0,0.8); text-align:center; line-height:1.5;';
            shield.appendChild(statusMsg);

            btnArea = document.createElement('div');
            btnArea.style.cssText = 'display:flex; gap:12px; justify-content:center; align-items:center;';

            const cancelBtn = document.createElement('button');
            cancelBtn.innerText = '⏹ 中止';
            cancelBtn.style.cssText = 'padding:10px 24px; border:none; border-radius:8px; background:#e74c3c; color:#fff; font-weight:bold; cursor:pointer; font-size:13px;';
            cancelBtn.onclick = () => { scrollCancelled = true; removeShield(); };
            btnArea.appendChild(cancelBtn);
            shield.appendChild(btnArea);
        }

        let lastHeight = 0;
        let topRetries = 0;
        while (topRetries < 3 && !scrollCancelled) {
            if (scrollableNode === window) window.scrollTo(0, 0);
            else scrollableNode.scrollTop = 0;
            await new Promise(r => setTimeout(r, 400));
            let currentHeight = scrollableNode === window ? document.body.scrollHeight : scrollableNode.scrollHeight;
            if (currentHeight === lastHeight) topRetries++;
            else topRetries = 0;
            lastHeight = currentHeight;
        }

        let currentScroll = 0;
        while (!scrollCancelled) {
            let maxScroll = scrollableNode === window ? document.body.scrollHeight : scrollableNode.scrollHeight;
            let viewportHeight = scrollableNode === window ? window.innerHeight : scrollableNode.clientHeight;

            if (statusMsg) statusMsg.innerText = `⚡ メディア事前ロード巡回中...\n[ ${Math.floor(currentScroll)} / ${maxScroll} px ]`;
            if (currentScroll >= maxScroll - viewportHeight) break;

            currentScroll += 2800;
            if (currentScroll > maxScroll - viewportHeight) currentScroll = maxScroll - viewportHeight;

            if (scrollableNode === window) window.scrollTo(0, currentScroll);
            else scrollableNode.scrollTop = currentScroll;

            await new Promise(r => setTimeout(r, 200));
        }

        if (isStandalone && shield && shield.parentNode) {
            if (scrollCancelled) {
                removeShield();
            } else {
                statusMsg.innerText = '🎉 ⚡ 事前ロード（ウォームアップ巡回）が完了しました！';
                statusMsg.style.color = '#2ecc71';
                btnArea.innerHTML = '';

                const closeBtn = document.createElement('button');
                closeBtn.innerText = '防護シールドを閉じる';
                closeBtn.style.cssText = 'padding:11px 22px; border:none; border-radius:8px; background:#2ecc71; color:#fff; font-weight:bold; cursor:pointer; font-size:13px;';
                closeBtn.onclick = () => removeShield();

                const startFullBtn = document.createElement('button');
                startFullBtn.innerText = '🚀 このまま自動スクロール全取得を開始';
                startFullBtn.style.cssText = 'padding:11px 22px; border:none; border-radius:8px; background:#e67e22; color:#fff; font-weight:bold; cursor:pointer; font-size:13px;';
                startFullBtn.onclick = () => {
                    removeShield();
                    setTimeout(() => { autoScrollAndSend(null, false); }, 100);
                };

                btnArea.appendChild(closeBtn);
                btnArea.appendChild(startFullBtn);
            }
        }
    }

    // 🌟 2. 【一括ボタン】
    async function runFullPreloadAndSend(btn) {
        scrollCancelled = false;
        await fastPreloadScroll(false);

        if (!scrollCancelled) {
            setTimeout(() => { autoScrollAndSend(btn, true); }, 100);
        } else {
            removeShield();
        }
    }

    // 🌟 3. 【本番全取得 ＆ 送信エンジン】
    async function autoScrollAndSend(btn, isPipeline = false) {
        if (!isPipeline) scrollCancelled = false;
        globalMediaCache = {};
        globalCollectedTurns = [];
        capturedTurnSet = new Set();

        const shield = getOrCreateShield();

        const statusMsg = document.createElement('div');
        statusMsg.innerText = '🚀 最上部へ移動してログを展開中...';
        statusMsg.style.cssText = 'color:#fff; font-size:18px; font-weight:bold; margin-bottom:10px; text-shadow:0 2px 4px rgba(0,0,0,0.8); text-align:center; line-height:1.5;';
        shield.appendChild(statusMsg);

        const timerLabel = document.createElement('div');
        timerLabel.innerText = '⏱ 経過時間: 00:00';
        timerLabel.style.cssText = 'color:#fff; font-size:22px; font-weight:bold; margin-bottom:25px; font-family:monospace; text-shadow:0 2px 4px rgba(0,0,0,0.8); text-align:center; white-space:pre-line;';
        shield.appendChild(timerLabel);

        const cancelBtn = document.createElement('button');
        cancelBtn.innerText = '⏹ キャンセルして中止';
        cancelBtn.style.cssText = 'padding:12px 24px; border:none; border-radius:8px; background:#e74c3c; color:#fff; font-weight:bold; cursor:pointer;';

        let startTime = Date.now();
        let timerInterval = setInterval(() => {
            let elapsed = Math.floor((Date.now() - startTime) / 1000);
            let mins = Math.floor(elapsed / 60).toString().padStart(2, '0');
            let secs = (elapsed % 60).toString().padStart(2, '0');
            timerLabel.innerText = `⏱ 経過時間: ${mins}:${secs}`;
        }, 1000);

        cancelBtn.onclick = () => {
            scrollCancelled = true;
            statusMsg.innerText = '⏹ 中止中...';
            removeShield();
        };
        shield.appendChild(cancelBtn);

        const scrollableNode = findScrollableNode();

        let lastHeight = 0;
        let topRetries = 0;
        while (topRetries < 3 && !scrollCancelled) {
            if (scrollableNode === window) window.scrollTo(0, 0);
            else scrollableNode.scrollTop = 0;
            await new Promise(r => setTimeout(r, 400));
            let currentHeight = scrollableNode === window ? document.body.scrollHeight : scrollableNode.scrollHeight;
            if (currentHeight === lastHeight) topRetries++;
            else topRetries = 0;
            lastHeight = currentHeight;
        }

        let currentScroll = 0;
        while (!scrollCancelled) {
            let maxScroll = scrollableNode === window ? document.body.scrollHeight : scrollableNode.scrollHeight;
            let viewportHeight = scrollableNode === window ? window.innerHeight : scrollableNode.clientHeight;

            statusMsg.innerText = `🚀 [全取得巡回中]\n💬 取得会話: ${globalCollectedTurns.length} ターン | 🖼️ メディア: ${Object.keys(globalMediaCache).length} 個`;

            await captureVisibleTurnsOnTheFly();

            if (currentScroll >= maxScroll - viewportHeight) break;

            currentScroll += (isChatGPT || isAIOverview) ? 900 : 1000;
            if (currentScroll > maxScroll - viewportHeight) currentScroll = maxScroll - viewportHeight;

            if (scrollableNode === window) window.scrollTo(0, currentScroll);
            else scrollableNode.scrollTop = currentScroll;

            await new Promise(r => setTimeout(r, 250));
        }

        clearInterval(timerInterval);

        if (scrollCancelled) {
            removeShield();
            return;
        }

        if (globalCollectedTurns.length === 0) {
            statusMsg.innerText = "⚠️ 送信できる会話ログが見つかりませんでした。";
            cancelBtn.innerText = '防護シールドを閉じる';
            cancelBtn.onclick = () => removeShield();
            return;
        }

        statusMsg.innerText = '⏳ 時系列データ構築 ＆ AiReSystemへ一括送信中...';

        const nowIso = new Date().toISOString();
        const payload = {
            chat_title: getChatTitle(),
            ai_service: getAIServiceName(),
            url: window.location.href,
            true_start_time: nowIso,
            true_end_time: nowIso,
            conversations: globalCollectedTurns,
            sync_mode: 'full'
        };

        GM_xmlhttpRequest({
            method: 'POST',
            url: 'http://127.0.0.1:5000/log',
            headers: { 'Content-Type': 'application/json' },
            data: JSON.stringify(payload),
            timeout: 5000,
            onload: function (response) {
                if (response.status === 200) {
                    statusMsg.innerText = '🎉 完全同期保存が完了しました！';
                    statusMsg.style.color = '#2ecc71';

                    let elapsed = Math.floor((Date.now() - startTime) / 1000);
                    let mins = Math.floor(elapsed / 60);
                    let secs = elapsed % 60;

                    timerLabel.innerText = `⏱ 所要時間: ${mins}分${secs}秒\n💬 保存会話: ${globalCollectedTurns.length} ターン\n🖼️ 回収アセット: ${Object.keys(globalMediaCache).length} 個\n📂 保存先: ${getAIServiceName()} / ${getChatTitle()}`;

                    cancelBtn.innerText = '防護シールドを閉じる';
                    cancelBtn.style.backgroundColor = '#2ecc71';
                    cancelBtn.onclick = () => removeShield();
                } else {
                    statusMsg.innerText = `❌ 送信エラー (HTTP ${response.status})`;
                    statusMsg.style.color = '#e74c3c';
                    cancelBtn.onclick = () => removeShield();
                }
            },
            onerror: function () {
                statusMsg.innerText = '❌ サーバー未起動 (127.0.0.1:5000)';
                statusMsg.style.color = '#e74c3c';
                cancelBtn.onclick = () => removeShield();
            }
        });
    }

    setInterval(createPanel, 1000);

})();