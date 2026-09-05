/**
 * app.js - 메인 애플리케이션 상태 제어, 실존 3층 건물 연동 & OpenStreetMap 타일 지도
 */

class App {
  constructor() {
    this.viewer = null;
    this.speech = window.aiSpeechAgent;
    this.currentData = null;
    this.activeTab = '3d_view'; // '3d_view' | 'report'
    this.defaultMetrics = null;
    this.sliderTimer = null;
    this.scanCount = 0;
    this.lastLat = 37.448919;
    this.lastLng = 127.167702;
    this.map = null;
    this.manualRotationEnabled = false;
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

    // 1. 3D 뷰어 초기화
    this.viewer = new CadastralARViewer('three-canvas');
    this.viewer.init();

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

    // 3. 슬라이더 이벤트 바인딩
    this.bindSliderEvents();

    // 4. 초기 기본 위치 로드 (신구대학교 본관)
    await this.handleLocationSelect(this.lastLat, this.lastLng, false);

    // 5. 2D 지적 및 공간정보 지도 초기화 (클릭으로 건물 선택 지원)
    this.initCadastralMap();
  }

  // ★ 2D 지도 초기화 & 클릭 리스너 연결
  initCadastralMap() {
    try {
      this.map = new CadastralMap('map-container', (lat, lng) => {
        this.onMapBuildingClick(lat, lng);
      });
      this.map.init(this.lastLat, this.lastLng, 18);
      if (this.currentData && this.currentData.parcel) {
        this.map.updateParcel(
          this.currentData.parcel.polygon_coords,
          this.currentData.parcel.title,
          this.lastLat,
          this.lastLng
        );
      }
    } catch (err) {
      console.warn("CadastralMap init error:", err);
    }
  }

  // ★ 지도상에서 원하는 건물 클릭 시 3D 모델링 및 지적 정보 실시간 로드
  async onMapBuildingClick(lat, lng) {
    if (isNaN(lat) || isNaN(lng)) return;
    this.showLoading(true);

    try {
      if (this.map) {
        this.map.showClickMarker(lat, lng, '📍 건물 위치 분석 중...', '공식 지적도 및 건물 좌표 스냅 중');
      }

      await this.handleLocationSelect(lat, lng, true);

      // 사용자가 클릭한 건물의 3D 모델링을 한눈에 볼 수 있도록 3D 뷰어로 부드럽게 자동 전환
      setTimeout(() => {
        this.switchMainTab('3d_view');
      }, 400);
    } catch (err) {
      console.error("Building click error:", err);
    } finally {
      this.showLoading(false);
    }
  }

  // ★ GPS 현재 내 위치 가져오기 핸들러
  async locateUser() {
    if (!navigator.geolocation) {
      alert("이 브라우저 또는 기기는 GPS 위치 기능을 지원하지 않습니다.");
      return;
    }

    // 모바일 브라우저 보안 정책(HTTPS 필수) 체크
    if (!window.isSecureContext && location.hostname !== 'localhost' && location.hostname !== '127.0.0.1') {
      alert("⚠️ [위치 권한 안내]\n스마트폰 브라우저 보안 정책상 일반 HTTP 접속 시 브라우저가 위치(GPS) 권한 팝업을 차단합니다.\n\n해결 방법 (안드로이드 크롬):\n1. 주소창에 chrome://flags 접속\n2. 'unsafely-treat-insecure-origin-as-secure' 검색\n3. Enabled로 변경 후 하단 입력란에 http://" + location.host + " 입력\n4. Relaunch(재실행) 버튼 클릭\n\n또는 HTTPS 주소로 접속해 주세요.");
      return;
    }

    this.showLoading(true);
    navigator.geolocation.getCurrentPosition(
      async (pos) => {
        const lat = pos.coords.latitude;
        const lng = pos.coords.longitude;
        if (this.map) {
          this.map.showClickMarker(lat, lng, '📍 현재 내 위치', 'GPS 위성 실시간 좌표');
          if (this.map.map) {
            this.map.map.setView([lat, lng], 18);
          }
        }
        await this.handleLocationSelect(lat, lng, true);
        this.showLoading(false);
      },
      (err) => {
        this.showLoading(false);
        console.warn("Geolocation error:", err);
        if (err.code === 1) {
          alert("위치 권한이 거부되었습니다. 브라우저 설정에서 위치 권한을 허용해 주세요.");
        } else {
          alert(`현재 위치를 가져올 수 없습니다: ${err.message || 'GPS 신호 불안정'}`);
        }
      },
      {
        enableHighAccuracy: true,
        timeout: 10000,
        maximumAge: 0
      }
    );
  }

  // ★ V-World 정밀 지오코딩 주소/지번 검색
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

      await this.handleLocationSelect(lat, lng, true);

      this.switchMainTab('3d_view');
    } catch (err) {
      alert(`검색 실패: ${err.message || "주소를 확인해 주세요."}`);
    } finally {
      this.showLoading(false);
    }
  }

  async handleLocationSelect(lat, lng, showLoadingBadge = true, scanIndex = 0) {
    if (isNaN(lat) || isNaN(lng)) return;

    if (showLoadingBadge) this.showLoading(true);
    try {
      const res = await fetch('/api/analyze-parcel', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          lat,
          lng,
          scan_index: scanIndex
        })
      });
      const data = await res.json();
      this.currentData = data;
      this.originalData = JSON.parse(JSON.stringify(data));

      // ★ 공식 지적 및 건물 중심 좌표로 스냅된 정확한 위경도 반영
      if (data.parcel && data.parcel.lat && data.parcel.lng) {
        this.lastLat = Number(data.parcel.lat);
        this.lastLng = Number(data.parcel.lng);
      } else {
        this.lastLat = lat;
        this.lastLng = lng;
      }

      // 새로운 위치 로드 시 이전 건물 사용자 회전값 및 스케일 초기화 (기본 도로축 정렬 상태)
      if (this.viewer) {
        this.viewer.resetBuildingAlignment();
      }

      this.defaultMetrics = {
        bcr: data.legal_metrics.applied_bcr,
        far: data.legal_metrics.applied_far,
        floor_height: data.legal_metrics.floor_height_m || 3.2,
        floors: data.legal_metrics.estimated_floors || data.parcel.existing_floors || 4,
        solar_setback: data.parcel.is_gis_polygon ? false : (data.legal_metrics.solar_setback?.applied ?? false)
      };

      this.updateUI(data);
    } catch (e) {
      console.error('Location analysis failed:', e);
    } finally {
      if (showLoadingBadge) this.showLoading(false);
    }
  }

  // ★ 모바일 초정밀 GPS 수신
  fetchCurrentGPSLocation(showBadge = true) {
    if (!navigator.geolocation) {
      this.handleLocationSelect(this.lastLat, this.lastLng, showBadge);
      return;
    }

    if (showBadge) this.showLoading(true);

    const geoOptions = {
      enableHighAccuracy: true,
      timeout: 10000,
      maximumAge: 0
    };

    navigator.geolocation.getCurrentPosition(
      (position) => {
        const lat = position.coords.latitude;
        const lng = position.coords.longitude;
        if (!isNaN(lat) && !isNaN(lng)) {
          this.lastLat = lat;
          this.lastLng = lng;
          this.handleLocationSelect(lat, lng, showBadge);
        }
      },
      (error) => {
        console.warn('GPS position error or timeout:', error);
        this.handleLocationSelect(this.lastLat, this.lastLng, showBadge);
      },
      geoOptions
    );
  }

  // ★ 슬라이더 [기준값 복원] 기능 - 해당 건물의 실제 원본 층수/형상 1:1 완벽 복원
  resetSlidersToDefault() {
    if (!this.defaultMetrics || !this.originalData) return;

    const sBcr = document.getElementById('slider-bcr');
    const sFar = document.getElementById('slider-far');
    const sH = document.getElementById('slider-floor-height');
    const sSolar = document.getElementById('check-solar-setback');

    if (sBcr) sBcr.value = this.defaultMetrics.bcr;
    if (sFar) sFar.value = this.defaultMetrics.far;
    if (sH) sH.value = this.defaultMetrics.floor_height;
    if (sSolar) sSolar.checked = this.defaultMetrics.solar_setback;

    const valBcr = document.getElementById('val-bcr');
    const valFar = document.getElementById('val-far');
    const valH = document.getElementById('val-floor-height');

    if (valBcr) valBcr.textContent = `${this.defaultMetrics.bcr}%`;
    if (valFar) valFar.textContent = `${this.defaultMetrics.far}%`;
    if (valH) valH.textContent = `${Number(this.defaultMetrics.floor_height).toFixed(1)}m`;

    // 원본 건물 데이터로 1:1 롤백
    this.currentData = JSON.parse(JSON.stringify(this.originalData));
    this.viewer.updateMassing(this.currentData.massing_3d, this.currentData.legal_metrics, this.lastLat, this.lastLng);
    this.updateHUDMetrics(this.currentData.legal_metrics, this.currentData.massing_3d);
    this.updateReportTab(this.currentData);
  }

  // ★ 건축 법규 시뮬레이션 슬라이더 패널 접기/펼치기
  toggleSliderPanel() {
    const contentEl = document.getElementById('slider-grid-content');
    const iconEl = document.getElementById('slider-toggle-icon');
    if (!contentEl) return;
    const isHidden = contentEl.classList.contains('hidden');
    if (isHidden) {
      contentEl.classList.remove('hidden');
      if (iconEl) iconEl.className = 'fas fa-chevron-down text-cyan-400 text-[10px]';
    } else {
      contentEl.classList.add('hidden');
      if (iconEl) iconEl.className = 'fas fa-chevron-up text-cyan-400 text-[10px]';
    }
  }

  // ★ 화면 뷰/카메라 위치 초기화 핸들러
  resetView() {
    if (this.viewer) {
      this.viewer.resetView();
    }
  }

  toggleVoice() {
    if (this.currentData && this.currentData.ai_report && this.speech) {
      this.speech.toggle(this.currentData.ai_report.tts_script);
    }
  }

  async simulateCurrentSliders() {
    if (!this.currentData) return;

    const bcr = parseFloat(document.getElementById('slider-bcr')?.value || 60);
    const far = parseFloat(document.getElementById('slider-far')?.value || 200);
    const floorHeight = parseFloat(document.getElementById('slider-floor-height')?.value || 3.2);
    const solarSetback = document.getElementById('check-solar-setback')?.checked ?? (this.currentData?.parcel?.is_gis_polygon ? false : (this.currentData?.legal_metrics?.solar_setback?.applied ?? false));

    const valBcr = document.getElementById('val-bcr');
    const valFar = document.getElementById('val-far');
    const valH = document.getElementById('val-floor-height');

    if (valBcr) valBcr.textContent = `${bcr}%`;
    if (valFar) valFar.textContent = `${far}%`;
    if (valH) valH.textContent = `${floorHeight.toFixed(1)}m`;

    try {
      const res = await fetch('/api/simulate-custom', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          site_area_sqm: this.currentData.parcel.site_area_sqm,
          zoning: this.currentData.legal_metrics.zoning_name,
          custom_bcr: bcr,
          custom_far: far,
          floor_height_m: floorHeight,
          apply_solar_setback: solarSetback,
          polygon_coords: this.currentData.parcel.polygon_coords,
          existing_floors: this.currentData.parcel.existing_floors,
          bld_name: this.currentData.parcel.bld_name || this.currentData.parcel.title,
          is_gis_polygon: Boolean(this.currentData.parcel.is_gis_polygon)
        })
      });
      const simData = await res.json();
      
      this.currentData.legal_metrics = simData.legal_metrics;
      this.currentData.massing_3d = simData.massing_3d;
      this.currentData.ai_report = simData.ai_report;

      this.viewer.updateMassing(simData.massing_3d, simData.legal_metrics, this.lastLat, this.lastLng);
      this.updateHUDMetrics(simData.legal_metrics, simData.massing_3d);
      this.updateReportTab(this.currentData);
    } catch (e) {
      console.error('Simulation error:', e);
    }
  }

  updateUI(data) {
    const { parcel, legal_metrics, massing_3d, ai_report } = data;

    const titleEl = document.getElementById('hud-parcel-title');
    const addrEl = document.getElementById('hud-parcel-address');
    if (titleEl) titleEl.textContent = parcel.title || '현재 위치 지적 필지';
    if (addrEl) addrEl.textContent = parcel.address || '실시간 위치 파싱 중...';
    
    const zoningEl = document.getElementById('badge-zoning');
    const jimokEl = document.getElementById('badge-jimok');
    const areaEl = document.getElementById('badge-area');
    const gisBadge = document.getElementById('badge-gis');

    if (zoningEl) zoningEl.textContent = legal_metrics.zoning_name || '제2종일반주거지역';
    if (jimokEl) jimokEl.textContent = parcel.jimok || parcel.land_use || '대지 (대)';
    if (areaEl) areaEl.textContent = `${(parcel.site_area_sqm || 0).toLocaleString()} ㎡`;

    if (gisBadge) {
      if (parcel.is_gis_polygon) {
        const ptCount = (parcel.polygon_coords && parcel.polygon_coords.length > 1) ? (parcel.polygon_coords.length - 1) : (parcel.polygon_coords?.length || 0);
        gisBadge.innerHTML = `<i class="fas fa-draw-polygon text-purple-400"></i> 실측 GIS ${ptCount}각 모델`;
        gisBadge.classList.remove('hidden');
      } else {
        gisBadge.classList.add('hidden');
      }
    }

    const sliderBcr = document.getElementById('slider-bcr');
    const valBcr = document.getElementById('val-bcr');
    const defBcrBadge = document.getElementById('default-bcr-badge');

    if (sliderBcr) sliderBcr.value = legal_metrics.applied_bcr;
    if (valBcr) valBcr.textContent = `${legal_metrics.applied_bcr}%`;
    if (defBcrBadge) defBcrBadge.textContent = `(기준 ${this.defaultMetrics?.bcr || legal_metrics.applied_bcr}%)`;

    const sliderFar = document.getElementById('slider-far');
    const valFar = document.getElementById('val-far');
    const defFarBadge = document.getElementById('default-far-badge');

    if (sliderFar) sliderFar.value = legal_metrics.applied_far;
    if (valFar) valFar.textContent = `${legal_metrics.applied_far}%`;
    if (defFarBadge) defFarBadge.textContent = `(기준 ${this.defaultMetrics?.far || legal_metrics.applied_far}%)`;

    const sliderH = document.getElementById('slider-floor-height');
    const valH = document.getElementById('val-floor-height');
    if (sliderH) sliderH.value = legal_metrics.floor_height_m || 3.2;
    if (valH) valH.textContent = `${(legal_metrics.floor_height_m || 3.2).toFixed(1)}m`;

    const checkSolar = document.getElementById('check-solar-setback');
    if (checkSolar) checkSolar.checked = parcel.is_gis_polygon ? false : legal_metrics.solar_setback.applied;

    const rotSlider = document.getElementById('building-rot-slider');
    const rotVal = document.getElementById('building-rot-val');
    if (rotSlider) rotSlider.value = this.viewer?.userRotationDeg || 0;
    if (rotVal) rotVal.textContent = `${(this.viewer?.userRotationDeg || 0) >= 0 ? '+' : ''}${(this.viewer?.userRotationDeg || 0).toFixed(1)}°`;

    this.updateHUDMetrics(legal_metrics, massing_3d);
    // ★ 3D 뷰어 바닥에 실제 2D 공간 지도 연동 (lat, lng) 좌표 직접 전달
    this.viewer.updateMassing(massing_3d, legal_metrics, this.lastLat, this.lastLng);

    // ★ 2D 지도에도 현재 선택된 건물의 필지 및 마커 동기화
    if (this.map && parcel) {
      this.map.updateParcel(parcel.polygon_coords, parcel.title, this.lastLat, this.lastLng);
    }

    this.updateReportTab(data);
  }

  updateHUDMetrics(legal, massing) {
    const bld = massing.massing_building;
    const fEl = document.getElementById('metric-floors');
    const hEl = document.getElementById('metric-height');
    const baEl = document.getElementById('metric-bld-area');
    const gaEl = document.getElementById('metric-gross-area');

    if (fEl) fEl.textContent = `${bld.floors_count}F`;
    if (hEl) hEl.textContent = `${bld.total_height_m}m`;
    if (baEl) baEl.textContent = `${Math.round(bld.max_building_area_sqm).toLocaleString()}㎡`;
    if (gaEl) gaEl.textContent = `${Math.round(bld.max_floor_area_sqm).toLocaleString()}㎡`;
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

  bindSliderEvents() {
    const onSliderInput = () => {
      clearTimeout(this.sliderTimer);
      this.sliderTimer = setTimeout(() => this.simulateCurrentSliders(), 50);
    };

    const sBcr = document.getElementById('slider-bcr');
    const sFar = document.getElementById('slider-far');
    const sH = document.getElementById('slider-floor-height');
    const sSolar = document.getElementById('check-solar-setback');

    if (sBcr) sBcr.addEventListener('input', onSliderInput);
    if (sFar) sFar.addEventListener('input', onSliderInput);
    if (sH) sH.addEventListener('input', onSliderInput);
    if (sSolar) sSolar.addEventListener('change', () => this.simulateCurrentSliders());
  }

  switchMainTab(tab) {
    this.activeTab = tab;

    const tabBtns = document.querySelectorAll('.main-tab-btn');
    tabBtns.forEach(btn => {
      if (btn.dataset.tab === tab) {
        btn.className = 'main-tab-btn px-3 py-1.5 rounded-md text-xs font-bold transition-all bg-cyan-500/20 border border-cyan-400 text-cyan-300 cursor-pointer shadow-sm';
      } else {
        btn.className = 'main-tab-btn px-3 py-1.5 rounded-md text-xs font-medium text-slate-400 transition-all border border-transparent hover:text-cyan-300 cursor-pointer';
      }
    });

    const arContainer = document.getElementById('ar-container');
    const mapContainer = document.getElementById('map-container');
    const reportContainer = document.getElementById('report-container');

    if (arContainer) {
      arContainer.classList.add('hidden');
      arContainer.style.display = 'none';
    }
    if (mapContainer) {
      mapContainer.classList.add('hidden');
      mapContainer.style.display = 'none';
    }
    if (reportContainer) {
      reportContainer.classList.add('hidden');
      reportContainer.style.display = 'none';
    }

    if (tab === '3d_view' && arContainer) {
      arContainer.classList.remove('hidden');
      arContainer.style.display = 'block';
      if (this.viewer) {
        this.viewer.onWindowResize();
      }
    } else if (tab === 'map_view' && mapContainer) {
      mapContainer.classList.remove('hidden');
      mapContainer.style.display = 'block';
      if (this.map) {
        this.map.resize();
        if (this.currentData?.parcel?.polygon_coords) {
          this.map.updateParcel(
            this.currentData.parcel.polygon_coords,
            this.currentData.parcel.title,
            this.lastLat,
            this.lastLng
          );
        }
      }
    } else if (tab === 'report' && reportContainer) {
      reportContainer.classList.remove('hidden');
      reportContainer.style.display = 'block';
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
