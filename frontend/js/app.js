/**
 * app.js - 메인 애플리케이션 상태 제어 (2D 지도 중심 & 이동 없는 원클릭 토지/법규 분석)
 */

class App {
  constructor() {
    this.speech = window.aiSpeechAgent;
    this.currentData = null;
    this.originalData = null;
    this.activeTab = 'map_view'; // 'map_view' | 'report'
    this.lastLat = 37.448919;
    this.lastLng = 127.167702;
    this.map = null;
    this.layerMenuClosedAt = 0;
  }

  isLayerMenuClosing() {
    return (Date.now() - this.layerMenuClosedAt) < 400;
  }

  async init() {
    // 0. V-World API 키 사전 로드
    try {
      const cfgRes = await fetch('/api/config-status');
      if (cfgRes.ok) {
        const cfg = await cfgRes.json();
        if (cfg.vworld_api_key) {
          window.vworldApiKey = cfg.vworld_api_key;
        }
      }
    } catch (e) {
      console.warn("Config load error:", e);
    }

    // 1. 2D 지적 및 공간정보 지도 초기화 (클릭으로 토지 선택)
    this.initCadastralMap();

    // 2. TTS 상태 콜백 바인딩
    if (this.speech) {
      this.speech.onStateChange = (speaking) => {
        const voiceBtn = document.getElementById('btn-voice-briefing');
        const voiceIcon = document.getElementById('voice-icon');
        const voiceText = document.getElementById('voice-btn-text');
        const waveBox = document.getElementById('voice-wave-container');

        if (speaking) {
          if (voiceBtn) {
            voiceBtn.classList.add('border-emerald-400', 'bg-emerald-950/60');
            voiceBtn.classList.remove('border-cyan-500/40', 'bg-slate-900/80');
          }
          if (voiceIcon) voiceIcon.className = 'fas fa-volume-up text-emerald-400 text-lg';
          if (voiceText) voiceText.textContent = '브리핑 중단';
          if (waveBox) waveBox.classList.add('speaking');
        } else {
          if (voiceBtn) {
            voiceBtn.classList.remove('border-emerald-400', 'bg-emerald-950/60');
            voiceBtn.classList.add('border-cyan-500/40', 'bg-slate-900/80');
          }
          if (voiceIcon) voiceIcon.className = 'fas fa-volume-high text-cyan-400 text-lg';
          if (voiceText) voiceText.textContent = 'AI 법규 브리핑';
          if (waveBox) waveBox.classList.remove('speaking');
        }
      };
    }

    // 드롭다운 외부 클릭 시 메뉴 닫고 레이어 아이콘 버튼 복귀 (지도 클릭 시 필지 선택 방지)
    const handleOutsideClick = (e) => {
      const dropdown = document.getElementById('map-layer-dropdown');
      const btn = document.getElementById('btn-map-layer-menu');
      if (dropdown && !dropdown.classList.contains('hidden')) {
        if (!dropdown.contains(e.target) && (!btn || !btn.contains(e.target))) {
          this.layerMenuClosedAt = Date.now();
          dropdown.classList.add('hidden');
          if (btn) btn.classList.remove('hidden');
        }
      }
    };
    document.addEventListener('pointerdown', handleOutsideClick, true);
    document.addEventListener('click', handleOutsideClick, true);

    // 3. 지도 초기화 완료 (사용자가 지도 클릭 또는 주소 검색 시 필지 분석 시작)
  }

  // ★ 2D 지도 초기화 & 클릭 리스너 연결
  initCadastralMap() {
    try {
      this.map = new CadastralMap('map-container', (lat, lng, shouldPan) => {
        this.onMapParcelClick(lat, lng, shouldPan);
      });
      this.map.init(this.lastLat, this.lastLng, 18);
    } catch (err) {
      console.warn("CadastralMap init error:", err);
    }
  }

  // ★ 지도상에서 원하는 땅 클릭 시 화면 이동 없이 바로 그 땅의 정보를 분석 및 표출
  async onMapParcelClick(lat, lng, shouldPan = false) {
    if (isNaN(lat) || isNaN(lng)) return;
    if (this.isLayerMenuClosing()) return;
    this.showLoading(true);

    try {
      if (this.map) {
        this.map.showClickMarker(lat, lng, '📍 필지 분석 중...', '토지 지적도 및 법규 연동 중');
      }

      // 화면 이동 없이(shouldPan = false) 데이터 분석 및 화면 갱신
      await this.handleLocationSelect(lat, lng, true, shouldPan);
    } catch (err) {
      console.error("Parcel click error:", err);
    } finally {
      this.showLoading(false);
    }
  }

  // ★ 연속지적도(지적선/지번/지목) ON/OFF 토글
  toggleCadastralLayer() {
    if (!this.map) return;
    const isVisible = this.map.toggleCadastral();
    const btn = document.getElementById('btn-layer-cadastral');
    const badge = document.getElementById('cadastral-badge-status');
    if (isVisible) {
      if (btn) {
        btn.className = 'w-full px-2.5 py-1.5 rounded-lg text-xs font-bold transition-all flex items-center justify-between cursor-pointer bg-yellow-950/40 text-yellow-300 border border-yellow-500/40 hover:bg-yellow-900/50 shadow-sm';
      }
      if (badge) {
        badge.textContent = 'ON';
        badge.className = 'text-[10px] px-1.5 py-0.5 rounded font-extrabold bg-yellow-500/20 text-yellow-300 border border-yellow-400/50';
      }
    } else {
      if (btn) {
        btn.className = 'w-full px-2.5 py-1.5 rounded-lg text-xs font-medium transition-all flex items-center justify-between cursor-pointer text-slate-400 hover:text-slate-200 hover:bg-slate-800/80 border border-slate-700/60';
      }
      if (badge) {
        badge.textContent = 'OFF';
        badge.className = 'text-[10px] px-1.5 py-0.5 rounded font-semibold bg-slate-800 text-slate-400 border border-slate-700';
      }
    }
  }

  // ★ 화면 우상단 지도 레이어 드롭다운 메뉴 토글 (버튼 숨기고 선택지 표출)
  toggleMapLayerMenu(e) {
    if (e) e.stopPropagation();
    const btn = document.getElementById('btn-map-layer-menu');
    const dropdown = document.getElementById('map-layer-dropdown');
    if (dropdown) {
      const isHidden = dropdown.classList.contains('hidden');
      if (isHidden) {
        dropdown.classList.remove('hidden');
        if (btn) btn.classList.add('hidden');
      } else {
        dropdown.classList.add('hidden');
        if (btn) btn.classList.remove('hidden');
      }
    }
  }

  // ★ 지도 레이어 유형 설정 (일반 지도 vs 위성 지도)
  setMapLayerType(type) {
    if (!this.map) return;
    this.map.setMapType(type);

    const btnBase = document.getElementById('btn-layer-base');
    const btnSat = document.getElementById('btn-layer-satellite');
    const dropdown = document.getElementById('map-layer-dropdown');
    const btnMenu = document.getElementById('btn-map-layer-menu');

    if (type === 'satellite') {
      if (btnSat) {
        btnSat.className = 'w-full px-2.5 py-1.5 rounded-lg text-xs font-bold transition-all flex items-center gap-2 cursor-pointer bg-cyan-500/20 text-cyan-300 border border-cyan-400/50 shadow-sm';
        const satIcon = btnSat.querySelector('i');
        if (satIcon) satIcon.className = 'fas fa-satellite text-xs text-cyan-400';
      }
      if (btnBase) {
        btnBase.className = 'w-full px-2.5 py-1.5 rounded-lg text-xs font-semibold transition-all flex items-center gap-2 cursor-pointer text-slate-300 hover:text-cyan-300 hover:bg-slate-800/80 border border-transparent';
        const baseIcon = btnBase.querySelector('i');
        if (baseIcon) baseIcon.className = 'fas fa-map text-xs text-slate-400';
      }
    } else {
      if (btnBase) {
        btnBase.className = 'w-full px-2.5 py-1.5 rounded-lg text-xs font-bold transition-all flex items-center gap-2 cursor-pointer bg-cyan-500/20 text-cyan-300 border border-cyan-400/50 shadow-sm';
        const baseIcon = btnBase.querySelector('i');
        if (baseIcon) baseIcon.className = 'fas fa-map text-xs text-cyan-400';
      }
      if (btnSat) {
        btnSat.className = 'w-full px-2.5 py-1.5 rounded-lg text-xs font-semibold transition-all flex items-center gap-2 cursor-pointer text-slate-300 hover:text-cyan-300 hover:bg-slate-800/80 border border-transparent';
        const satIcon = btnSat.querySelector('i');
        if (satIcon) satIcon.className = 'fas fa-satellite text-xs text-slate-400';
      }
    }

    if (dropdown) {
      dropdown.classList.add('hidden');
    }
    if (btnMenu) {
      btnMenu.classList.remove('hidden');
    }
  }

  // ★ GPS 현재 내 위치 가져오기 핸들러
  async locateUser() {
    if (!navigator.geolocation) {
      alert("이 브라우저 또는 기기는 GPS 위치 기능을 지원하지 않습니다.");
      return;
    }

    this.showLoading(true);
    navigator.geolocation.getCurrentPosition(
      async (pos) => {
        const lat = pos.coords.latitude;
        const lng = pos.coords.longitude;
        if (this.map) {
          this.map.showClickMarker(lat, lng, '📍 현재 내 위치', 'GPS 위성 실시간 좌표');
          this.map.flyTo(lat, lng, 18);
        }
        await this.handleLocationSelect(lat, lng, true, false);
        this.showLoading(false);
      },
      (err) => {
        this.showLoading(false);
        console.warn("Geolocation error:", err);
        alert(`위치를 가져올 수 없습니다: ${err.message || 'GPS 신호 불안정'}`);
      },
      {
        enableHighAccuracy: true,
        timeout: 10000,
        maximumAge: 0
      }
    );
  }

  // ★ V-World 정밀 지오코딩 주소/지번 검색 (검색 시에는 해당 위치로 이동)
  async searchAndGoAddress() {
    const inputEl = document.getElementById('input-address-search');
    if (!inputEl) return;
    const query = inputEl.value.trim();
    if (!query) {
      alert("검색할 주소 또는 건물명을 입력해 주세요 (예: 신구대학교, 63빌딩, 테헤란로 152).");
      return;
    }

    this.showLoading(true);
    try {
      const res = await fetch(`/api/search-location?q=${encodeURIComponent(query)}`);
      if (!res.ok) {
        throw new Error("주소 결과를 찾을 수 없습니다.");
      }
      const data = await res.json();
      const lat = parseFloat(data.lat);
      const lng = parseFloat(data.lng);

      if (isNaN(lat) || isNaN(lng) || !lat || !lng) {
        throw new Error("유효한 좌표를 파싱할 수 없습니다.");
      }

      if (this.map) {
        this.map.flyTo(lat, lng, 18);
      }

      await this.handleLocationSelect(lat, lng, true, false);
      this.switchMainTab('map_view');
    } catch (err) {
      alert(`검색 실패: ${err.message || "주소를 확인해 주세요."}`);
    } finally {
      this.showLoading(false);
    }
  }

  async handleLocationSelect(lat, lng, showLoadingBadge = true, shouldPan = false) {
    if (isNaN(lat) || isNaN(lng)) return;

    if (showLoadingBadge) this.showLoading(true);
    try {
      const res = await fetch('/api/analyze-parcel', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          lat,
          lng,
          scan_index: 0
        })
      });
      const data = await res.json();
      this.currentData = data;
      this.originalData = JSON.parse(JSON.stringify(data));

      this.lastLat = lat;
      this.lastLng = lng;

      this.updateUI(data, shouldPan);
    } catch (e) {
      console.error('Location analysis failed:', e);
    } finally {
      if (showLoadingBadge) this.showLoading(false);
    }
  }

  // ★ 화면 뷰 초기화 (기본 위치 복귀)
  resetView() {
    if (this.map) {
      this.map.flyTo(37.448919, 127.167702, 18);
      this.handleLocationSelect(37.448919, 127.167702, true, false);
    }
  }

  toggleVoice() {
    if (this.currentData && this.currentData.ai_report && this.speech) {
      this.speech.toggle(this.currentData.ai_report.tts_script);
    }
  }

  updateUI(data, shouldPan = false) {
    const { parcel, legal_metrics, massing_3d, ai_report } = data;

    const titleEl = document.getElementById('hud-parcel-title');
    const addrEl = document.getElementById('hud-parcel-address');
    if (titleEl) titleEl.textContent = parcel.title || '선택된 지적 필지';
    if (addrEl) addrEl.textContent = parcel.address || '실시간 위치 파싱 중...';
    
    const zoningEl = document.getElementById('badge-zoning');
    const jimokEl = document.getElementById('badge-jimok');
    const areaEl = document.getElementById('badge-area');

    if (zoningEl) zoningEl.textContent = legal_metrics.zoning_name || '제2종일반주거지역';
    const cleanJimok = (parcel.jimok && parcel.jimok !== '-' && parcel.jimok.trim() !== '') ? parcel.jimok : (parcel.land_use || '대지 (대)');
    if (jimokEl) jimokEl.textContent = cleanJimok;
    if (areaEl) areaEl.textContent = `${(parcel.site_area_sqm || 0).toLocaleString()} ㎡`;

    this.updateHUDMetrics(legal_metrics, massing_3d);

    // ★ 2D 지도에 선택된 땅의 경계 폴리곤 및 마커 즉시 업데이트 (화면 강제 이동 없음)
    if (this.map && parcel) {
      this.map.updateParcel(
        parcel.polygon_coords,
        parcel.title,
        this.lastLat,
        this.lastLng,
        shouldPan,
        parcel
      );
    }

    this.updateReportTab(data);
  }

  updateHUDMetrics(legal, massing) {
    const bcrEl = document.getElementById('metric-bcr');
    const farEl = document.getElementById('metric-far');

    if (legal) {
      if (bcrEl && legal.applied_bcr !== undefined) {
        bcrEl.textContent = `${legal.applied_bcr}%`;
      }
      if (farEl && legal.applied_far !== undefined) {
        farEl.textContent = `${legal.applied_far}%`;
      }
    }
  }

  updateReportTab(data) {
    if (!data || !data.ai_report) return;
    const { parcel, legal_metrics, ai_report } = data;

    const evalEl = document.getElementById('report-ai-eval');
    if (evalEl) evalEl.textContent = ai_report.ai_evaluation;

    const container = document.getElementById('report-sections-container');
    if (container) {
      container.innerHTML = '';
      (ai_report.report_sections || []).forEach(sec => {
        const secBox = document.createElement('div');
        secBox.className = 'glass-panel p-4 rounded-xl border border-cyan-500/20';

        let itemsHtml = sec.items.map(item => `
          <div class="flex justify-between items-center py-2 border-b border-slate-700/40 text-xs md:text-sm">
            <span class="text-slate-400 font-medium">${item.label}</span>
            <span class="text-cyan-300 font-semibold text-right">${item.value}</span>
          </div>
        `).join('');

        secBox.innerHTML = `
          <h4 class="text-sm md:text-base font-bold text-cyan-400 mb-2 flex items-center gap-2">
            <i class="fas fa-check-circle text-xs text-cyan-400"></i> ${sec.category}
          </h4>
          <div class="space-y-0.5">
            ${itemsHtml}
          </div>
        `;
        container.appendChild(secBox);
      });
    }

    const ttsPrev = document.getElementById('report-tts-preview');
    if (ttsPrev) ttsPrev.textContent = ai_report.tts_script;
  }

  // ★ 법규 리포트 토글 (지도 뷰 <-> 리포트 오버레이)
  toggleReportView() {
    const nextTab = this.activeTab === 'report' ? 'map_view' : 'report';
    this.switchMainTab(nextTab);
  }

  switchMainTab(tab) {
    this.activeTab = tab;

    const reportBtn = document.getElementById('main-tab-report');
    const reportContainer = document.getElementById('report-container');
    const mapLayerContainer = document.getElementById('map-layer-container');
    const btnMenu = document.getElementById('btn-map-layer-menu');
    const dropdown = document.getElementById('map-layer-dropdown');

    if (tab === 'map_view') {
      if (reportBtn) {
        reportBtn.className = 'px-3 py-1.5 rounded-lg glass-panel border border-cyan-500/40 hover:border-cyan-400 bg-slate-900/90 hover:bg-cyan-950/80 text-cyan-300 font-bold text-xs shadow-md flex items-center gap-1.5 active:scale-95 transition-all cursor-pointer whitespace-nowrap shrink-0';
      }
      if (reportContainer) {
        reportContainer.classList.add('hidden');
      }
      if (mapLayerContainer) {
        mapLayerContainer.classList.remove('hidden');
      }
      if (btnMenu) {
        btnMenu.classList.remove('hidden');
      }
      if (dropdown) {
        dropdown.classList.add('hidden');
      }
      if (this.map) {
        this.map.resize();
      }
    } else if (tab === 'report') {
      if (reportBtn) {
        reportBtn.className = 'px-3 py-1.5 rounded-lg glass-panel border border-cyan-400 bg-cyan-500/20 text-cyan-200 font-bold text-xs shadow-md flex items-center gap-1.5 active:scale-95 transition-all cursor-pointer whitespace-nowrap shrink-0';
      }
      if (reportContainer) {
        reportContainer.classList.remove('hidden');
      }
      if (mapLayerContainer) {
        mapLayerContainer.classList.add('hidden');
      }
      if (this.currentData) {
        this.updateReportTab(this.currentData);
      }
    }
  }

  showLoading(show) {
    const el = document.getElementById('loading-badge');
    if (!el) return;
    if (show) {
      el.classList.remove('hidden');
    } else {
      el.classList.add('hidden');
    }
  }
}

window.addEventListener('DOMContentLoaded', () => {
  window.app = new App();
  window.app.init();
});
