/**
 * speech.js - Web Speech API 기반 AI 법규 브리핑 음성 합성(TTS) 모듈
 */

class AISpeechAgent {
  constructor() {
    this.synth = window.speechSynthesis;
    this.utterance = null;
    this.isSpeaking = false;
    this.onStateChange = null;
    this.selectedVoice = null;

    if (this.synth) {
      this.initVoices();
      if (speechSynthesis.onvoiceschanged !== undefined) {
        speechSynthesis.onvoiceschanged = () => this.initVoices();
      }
    }
  }

  initVoices() {
    if (!this.synth) return;
    const voices = this.synth.getVoices();
    // 한국어 음성 우선 선택 (예: Google 한국어, Yuna, Heami 등)
    this.selectedVoice = voices.find(v => v.lang.includes('ko') || v.lang.includes('KR')) || voices[0];
  }

  speak(text) {
    if (!this.synth) {
      alert("이 브라우저는 음성 합성(Web Speech API)을 지원하지 않습니다.");
      return;
    }

    // 기존 발화 중단
    this.stop();

    if (!text || text.trim() === '') return;

    this.utterance = new SpeechSynthesisUtterance(text);
    if (this.selectedVoice) {
      this.utterance.voice = this.selectedVoice;
    }
    this.utterance.lang = 'ko-KR';
    this.utterance.rate = 1.02; // 약간 또렷한 템포
    this.utterance.pitch = 1.0;

    this.utterance.onstart = () => {
      this.isSpeaking = true;
      if (this.onStateChange) this.onStateChange(true);
    };

    this.utterance.onend = () => {
      this.isSpeaking = false;
      if (this.onStateChange) this.onStateChange(false);
    };

    this.utterance.onerror = (e) => {
      console.warn("TTS Error:", e);
      this.isSpeaking = false;
      if (this.onStateChange) this.onStateChange(false);
    };

    this.synth.speak(this.utterance);
  }

  pause() {
    if (this.synth && this.synth.speaking) {
      this.synth.pause();
    }
  }

  resume() {
    if (this.synth && this.synth.paused) {
      this.synth.resume();
    }
  }

  stop() {
    if (this.synth) {
      this.synth.cancel();
      this.isSpeaking = false;
      if (this.onStateChange) this.onStateChange(false);
    }
  }

  toggle(text) {
    if (this.isSpeaking) {
      this.stop();
    } else {
      this.speak(text);
    }
  }
}

window.aiSpeechAgent = new AISpeechAgent();
