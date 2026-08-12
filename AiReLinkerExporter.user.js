// ==UserScript==
// @name         AiReLinker Universal Chat Sync Button
// @namespace    http://tampermonkey.net/
// @version      1.2
// @description  1-Click Sync ChatGPT, Gemini, Claude, AI Studio, Perplexity, NotebookLM chats to AiReLinker (with Image Support)
// @author       Your Assistant
// @match        https://gemini.google.com/*
// @match        https://aistudio.google.com/*
// @match        https://chatgpt.com/*
// @match        https://claude.ai/*
// @match        https://www.perplexity.ai/*
// @match        https://notebooklm.google.com/*
// @match        https://genspark.ai/*
// @match        https://*.google.com/notebooks*
// @grant        GM_xmlhttpRequest
// @connect      localhost
// ==/UserScript==

(function() {
    'use strict';

    // 画像をBase64に変換するヘルパー関数
    async function getImageBase64(imgElement) {
        return new Promise((resolve) => {
            const canvas = document.createElement("canvas");
            canvas.width = imgElement.naturalWidth;
            canvas.height = imgElement.naturalHeight;
            const ctx = canvas.getContext("2d");
            ctx.drawImage(imgElement, 0, 0);
            try {
                resolve(canvas.toDataURL("image/png").split(',')[1]); // ヘッダーを除いたBase64部分のみ
            } catch (e) {
                console.error("Image conversion failed", e);
                resolve(null);
            }
        });
    }

    const btn = document.createElement('button');
    btn.innerHTML = '💾 AiReLinkerに同期';
    btn.style.position = 'fixed';
    btn.style.bottom = '20px';
    btn.style.right = '20px';
    btn.style.zIndex = '99999';
    btn.style.padding = '10px 14px';
    btn.style.backgroundColor = '#10a37f';
    btn.style.color = '#fff';
    btn.style.border = 'none';
    btn.style.borderRadius = '6px';
    btn.style.cursor = 'pointer';
    btn.style.fontWeight = 'bold';
    btn.style.boxShadow = '0 4px 12px rgba(0,0,0,0.15)';
    btn.style.fontFamily = 'sans-serif';
    btn.style.fontSize = '12px';
    
    btn.onmouseover = () => btn.style.backgroundColor = '#1a7f64';
    btn.onmouseout = () => btn.style.backgroundColor = '#10a37f';
    document.body.appendChild(btn);

    btn.addEventListener('click', async () => {
        btn.innerHTML = '⏳ 同期中...';
        btn.style.backgroundColor = '#f39c12';
        
        try {
            let conversations = [];
            let host = window.location.hostname;
            
            if (host.includes('aistudio.google.com')) {
                // AI Studio: テキストと画像を両方抽出
                const bubbles = document.querySelectorAll('.chat-bubble, .message-content');
                for (const b of bubbles) {
                    let role = b.classList.contains('user') || b.placeholder?.includes('User') ? 'user' : 'model';
                    let parts = [];
                    
                    // テキスト抽出
                    let text = b.innerText?.trim();
                    if (text) parts.push({ text: text });
                    
                    // 画像抽出
                    const imgs = b.querySelectorAll('img');
                    for (const img of imgs) {
                        const b64 = await getImageBase64(img);
                        if (b64) {
                            parts.push({
                                inlineData: {
                                    mimeType: "image/png",
                                    data: b64
                                }
                            });
                        }
                    }
                    if (parts.length > 0) conversations.push({ role: role, parts: parts });
                }
            } else if (host.includes('gemini.google.com')) {
                // Gemini Web
                const queries = document.querySelectorAll('.query-text');
                const replies = document.querySelectorAll('.model-response-text');
                let len = Math.max(queries.length, replies.length);
                for(let i=0; i<len; i++) {
                    if(queries[i]) conversations.push({role: 'user', parts: [{text: queries[i].innerText}]});
                    if(replies[i]) conversations.push({role: 'model', parts: [{text: replies[i].innerText}]});
                }
            } else if (host.includes('chatgpt.com')) {
                // ChatGPT
                const messages = document.querySelectorAll('[data-testid^="conversation-turn"]');
                messages.forEach(msg => {
                    const isUser = msg.querySelector('[data-testid="user-message"]') || msg.innerText.includes('あなた');
                    const textEl = msg.querySelector('.markdown') || msg;
                    let parts = [];
                    if (textEl) parts.push({ text: textEl.innerText });
                    
                    const imgs = msg.querySelectorAll('img');
                    // ChatGPTの画像は複雑なため、ここではURLを保持させるか、後で拡張
                    conversations.push({ role: isUser ? 'user' : 'model', parts: parts });
                });
            } else {
                // 汎用
                conversations.push({
                    role: 'user',
                    parts: [{ text: `【自動抽出ログ: ${document.title}】\n\n` + document.body.innerText.substring(0, 50000) }]
                });
            }

            if (conversations.length === 0) {
                alert('チャットメッセージを検出できませんでした。');
                btn.innerHTML = '💾 再試行';
                btn.style.backgroundColor = '#e74c3c';
                return;
            }

            const payload = {
                url: window.location.href,
                chat_title: document.title, // キー名をサーバーに合わせて "chat_title" に変更
                true_start_time: new Date().toISOString(),
                true_end_time: new Date().toISOString(),
                conversations: conversations
            };

            GM_xmlhttpRequest({
                method: "POST",
                url: "http://localhost:5000/log",
                data: JSON.stringify(payload),
                headers: { "Content-Type": "application/json" },
                onload: function(response) {
                    if (response.status === 200) {
                        btn.innerHTML = '✅ 同期完了';
                        btn.style.backgroundColor = '#2ecc71';
                        setTimeout(() => {
                            btn.innerHTML = '💾 AiReLinkerに同期';
                            btn.style.backgroundColor = '#10a37f';
                        }, 3000);
                    } else {
                        throw new Error("Server error: " + response.status);
                    }
                },
                onerror: function(err) {
                    alert('サーバーが起動していないか、通信エラーです。');
                    btn.innerHTML = '❌ 失敗';
                    btn.style.backgroundColor = '#e74c3c';
                }
            });

        } catch (e) {
            console.error(e);
            alert('同期処理中にエラーが発生しました: ' + e.message);
            btn.innerHTML = '❌ エラー';
            btn.style.backgroundColor = '#e74c3c';
        }
    });
})();