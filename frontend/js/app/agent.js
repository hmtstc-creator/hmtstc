window.HMTSTC_APP_AGENT = {
  getSpeechRecognition: function () {
    return window.SpeechRecognition || window.webkitSpeechRecognition || null;
  },

  canUseVoice: function () {
    return Boolean(this.getSpeechRecognition()) && Boolean(window.speechSynthesis);
  },

  speakAgentText: function (text, onEnd) {
    if (!window.speechSynthesis || !text) {
      if (typeof onEnd === "function") {
        onEnd();
      }
      return;
    }

    try {
      window.speechSynthesis.cancel();

      const utterance = new SpeechSynthesisUtterance(text);

      utterance.lang = "tr-TR";
      utterance.rate = 1;
      utterance.pitch = 1;
      utterance.volume = 1;

      utterance.onstart = function () {
        HMTSTC_APP.state.agentVoiceSpeaking = true;
        HMTSTC_APP.render();
      };

      utterance.onend = function () {
        HMTSTC_APP.state.agentVoiceSpeaking = false;
        HMTSTC_APP.render();

        if (typeof onEnd === "function") {
          onEnd();
        }
      };

      utterance.onerror = function () {
        HMTSTC_APP.state.agentVoiceSpeaking = false;
        HMTSTC_APP.render();

        if (typeof onEnd === "function") {
          onEnd();
        }
      };

      window.speechSynthesis.speak(utterance);

    } catch (error) {
      console.error("Jarvis sesli yanıt hatası:", error);
      HMTSTC_APP.state.agentVoiceSpeaking = false;
      HMTSTC_APP.render();

      if (typeof onEnd === "function") {
        onEnd();
      }
    }
  },

  stopAgentVoice: function () {
    try {
      if (window.speechSynthesis) {
        window.speechSynthesis.cancel();
      }
    } catch (error) {
      console.error("Jarvis ses durdurma hatası:", error);
    }

    HMTSTC_APP.state.agentVoiceSpeaking = false;
    HMTSTC_APP.state.agentVoiceListening = false;
    HMTSTC_APP.state.agentConversationMode = false;
    HMTSTC_APP.render();
  },

  toggleAgentAutoSpeak: function () {
    HMTSTC_APP.state.agentAutoSpeak = !HMTSTC_APP.state.agentAutoSpeak;
    HMTSTC_APP.render();
  },

  toggleAgentConversationMode: function () {
    HMTSTC_APP.state.agentConversationMode =
      !HMTSTC_APP.state.agentConversationMode;

    HMTSTC_APP.render();

    if (HMTSTC_APP.state.agentConversationMode) {
      this.startVoiceAgent();
    } else {
      this.stopAgentVoice();
    }
  },

  sendAgentMessage: async function () {
    const input = document.getElementById("agent-message-input");
    const message = input ? input.value.trim() : "";

    if (!message) {
      return;
    }

    if (!HMTSTC_APP.state.auth) {
      HMTSTC_APP.state.agentLastError = "Oturum yok. Mesaj gönderilemedi.";
      HMTSTC_APP.render();
      return;
    }

    HMTSTC_APP.state.agentThinking = true;
    HMTSTC_APP.state.agentLastError = "";

    HMTSTC_DATA.agentChat = Array.isArray(HMTSTC_DATA.agentChat)
      ? HMTSTC_DATA.agentChat
      : [];

    HMTSTC_DATA.agentChat.push({
      role: "user",
      time: new Date().toISOString(),
      message: message
    });

    if (input) {
      input.value = "";
    }

    HMTSTC_APP.render();

    try {
      const result = await HMTSTC_APP.fetchJson("/api/agent/chat", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "Cache-Control": "no-store"
        },
        body: JSON.stringify({ message: message })
      });

      HMTSTC_DATA.agentChat = Array.isArray(result.messages)
        ? result.messages
        : HMTSTC_DATA.agentChat;

      if (result.report) {
        HMTSTC_DATA.agentReport = result.report;
      }

      HMTSTC_APP.state.agentThinking = false;
      HMTSTC_APP.render();

      const answer = result.answer || "";

      if (HMTSTC_APP.state.agentAutoSpeak && answer) {
        this.speakAgentText(answer, function () {
          if (HMTSTC_APP.state.agentConversationMode) {
            setTimeout(function () {
              HMTSTC_APP.startVoiceAgent();
            }, 450);
          }
        });
      } else if (HMTSTC_APP.state.agentConversationMode) {
        setTimeout(function () {
          HMTSTC_APP.startVoiceAgent();
        }, 450);
      }

    } catch (error) {
      console.error("Jarvis mesaj hatası:", error);
      HMTSTC_APP.state.agentThinking = false;
      HMTSTC_APP.state.agentLastError = "Jarvis yanıtı alınamadı.";
      HMTSTC_APP.render();
    }
  },

  createAgentReport: async function () {
    if (!HMTSTC_APP.state.auth) {
      HMTSTC_APP.state.agentLastError = "Oturum yok. Rapor üretilemedi.";
      HMTSTC_APP.render();
      return;
    }

    HMTSTC_APP.state.agentThinking = true;
    HMTSTC_APP.state.agentLastError = "";
    HMTSTC_APP.render();

    try {
      const result = await HMTSTC_APP.fetchJson("/api/agent/report", {
        method: "POST"
      });

      HMTSTC_DATA.agentReport = result;
      HMTSTC_APP.pushOperationLine(
        "Jarvis paper raporu üretildi: " + (result.action || "report")
      );

      if (HMTSTC_APP.state.agentAutoSpeak && result.summary) {
        this.speakAgentText(result.summary);
      }

      await HMTSTC_APP.syncApiData();

    } catch (error) {
      console.error("Jarvis rapor hatası:", error);
      HMTSTC_APP.state.agentLastError = "Jarvis raporu üretilemedi.";

    } finally {
      HMTSTC_APP.state.agentThinking = false;
      HMTSTC_APP.render();
    }
  },

  fillAgentPrompt: function (message) {
    const input = document.getElementById("agent-message-input");

    if (input) {
      input.value = message;
      input.focus();
    }
  },

  startVoiceAgent: function () {
    const SpeechRecognition = this.getSpeechRecognition();

    if (!SpeechRecognition) {
      HMTSTC_APP.state.agentLastError =
        "Bu tarayıcı sesli komutu desteklemiyor.";
      HMTSTC_APP.render();
      return;
    }

    if (HMTSTC_APP.state.agentVoiceListening) {
      return;
    }

    try {
      if (window.speechSynthesis) {
        window.speechSynthesis.cancel();
      }
    } catch (error) {
      console.error("Speech cancel hatası:", error);
    }

    const recognition = new SpeechRecognition();

    recognition.lang = "tr-TR";
    recognition.interimResults = false;
    recognition.continuous = false;
    recognition.maxAlternatives = 1;

    HMTSTC_APP.state.agentVoiceListening = true;
    HMTSTC_APP.state.agentVoiceSpeaking = false;
    HMTSTC_APP.state.agentLastError = "";
    HMTSTC_APP.render();

    recognition.onresult = function (event) {
      const transcript =
        event &&
        event.results &&
        event.results[0] &&
        event.results[0][0]
          ? event.results[0][0].transcript
          : "";

      const input = document.getElementById("agent-message-input");

      if (input) {
        input.value = transcript;
      }

      HMTSTC_APP.state.agentVoiceListening = false;
      HMTSTC_APP.render();

      if (transcript) {
        HMTSTC_APP.sendAgentMessage();
      }
    };

    recognition.onerror = function () {
      HMTSTC_APP.state.agentVoiceListening = false;
      HMTSTC_APP.state.agentLastError = "Sesli komut alınamadı.";
      HMTSTC_APP.render();
    };

    recognition.onend = function () {
      HMTSTC_APP.state.agentVoiceListening = false;
      HMTSTC_APP.render();
    };

    recognition.start();
  }
};