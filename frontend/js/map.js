/**
 * map.js - Leaflet 기반 지적도 및 공간정보 지도 뷰어 (클릭으로 건물 선택 & 3D 연동)
 */

class CadastralMap {
  constructor(mapContainerId, onParcelSelect) {
    this.containerId = mapContainerId;
    this.onParcelSelect = onParcelSelect;
    this.map = null;
    this.baseLayer = null;
    this.satelliteLayer = null;
    this.hybridLayer = null;
    this.cadastralLayer = null;
    this.zoningLayer = null;
    this.polygonLayer = null;
    this.markerLayer = null;
    this.currentMarker = null;
    this.isCadastralVisible = true;
    this.currentMapType = 'base'; // 'base' | 'satellite'
  }

  init(defaultLat = 37.448919, defaultLng = 127.167702, zoom = 18) {
    if (this.map) return;
    if (typeof L === 'undefined') {
      console.warn("Leaflet library not loaded yet.");
      return;
    }

    const container = document.getElementById(this.containerId);
    if (!container) return;

    this.map = L.map(this.containerId, {
      zoomControl: false,
      attributionControl: false,
      minZoom: 7,
      maxZoom: 19
    }).setView([defaultLat, defaultLng], zoom);

    // 0. GPS 내 위치 버튼 (줌 컨트롤 상단 배치)
    const LocateControl = L.Control.extend({
      options: { position: 'bottomright' },
      onAdd: function(map) {
        const btn = L.DomUtil.create('button', 'leaflet-control-custom-locate');
        btn.innerHTML = '<i class="fas fa-crosshairs text-cyan-400 text-sm"></i>';
        btn.title = '현재 내 GPS 위치로 이동';
        btn.onclick = function(e) {
          e.stopPropagation();
          e.preventDefault();
          if (window.app && window.app.locateUser) {
            window.app.locateUser();
          }
        };
        return btn;
      }
    });
    new LocateControl().addTo(this.map);

    L.control.zoom({ position: 'bottomright' }).addTo(this.map);

    const vworldKey = window.vworldApiKey || "DEB860E4-52DC-35F3-9E68-664B22DF3592";
    const currentHost = window.location.hostname;
    const domainParam = (currentHost === '127.0.0.1' || !currentHost) ? 'localhost' : currentHost;

    // 1. 기본 배경지도 (V-World Base - 최대 19레벨)
    this.baseLayer = L.tileLayer(`https://api.vworld.kr/req/wmts/1.0.0/${vworldKey}/Base/{z}/{y}/{x}.png`, {
      minZoom: 7,
      maxZoom: 19,
      maxNativeZoom: 19,
      errorTileUrl: 'https://tile.openstreetmap.org/{z}/{x}/{y}.png'
    }).addTo(this.map);

    // 2. 항공/위성 영상지도 (V-World Satellite - 최대 19레벨)
    this.satelliteLayer = L.tileLayer(`https://api.vworld.kr/req/wmts/1.0.0/${vworldKey}/Satellite/{z}/{y}/{x}.jpeg`, {
      minZoom: 7,
      maxZoom: 19,
      maxNativeZoom: 19,
      errorTileUrl: 'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}'
    });

    // 3. 하이브리드 명칭/도로 레이어
    this.hybridLayer = L.tileLayer(`https://api.vworld.kr/req/wmts/1.0.0/${vworldKey}/Hybrid/{z}/{y}/{x}.png`, {
      minZoom: 7,
      maxZoom: 19,
      maxNativeZoom: 19,
      zIndex: 5
    });

    // 4. 국토교통부 V-World WMS 연속지적도 (지적선 경계 및 지번)
    this.cadastralLayer = L.tileLayer.wms('https://api.vworld.kr/req/wms', {
      service: 'WMS',
      version: '1.3.0',
      request: 'GetMap',
      layers: 'lp_pa_cbnd_bubun,lp_pa_cbnd_bonbun',
      styles: 'lp_pa_cbnd_bubun,lp_pa_cbnd_bonbun',
      format: 'image/png',
      transparent: true,
      crs: L.CRS.EPSG3857,
      key: vworldKey,
      domain: domainParam,
      minZoom: 10,
      maxZoom: 19,
      maxNativeZoom: 19,
      opacity: 0.9,
      zIndex: 10
    });

    // 기본으로 연속지적도 활성화
    if (this.isCadastralVisible) {
      this.cadastralLayer.addTo(this.map);
    }

    this.polygonLayer = L.layerGroup().addTo(this.map);
    this.markerLayer = L.layerGroup().addTo(this.map);

    // 지도 클릭 시 화면 이동 없이 해당 위치의 필지/토지 정보 조회
    this.map.on('click', (e) => {
      const dropdown = document.getElementById('map-layer-dropdown');
      if (dropdown && !dropdown.classList.contains('hidden')) {
        return;
      }
      if (window.app && window.app.isLayerMenuClosing && window.app.isLayerMenuClosing()) {
        return;
      }
      const { lat, lng } = e.latlng;
      this.showClickMarker(lat, lng);
      if (this.onParcelSelect) {
        this.onParcelSelect(lat, lng, false);
      }
    });

    setTimeout(() => {
      if (this.map) this.map.invalidateSize();
    }, 200);
  }

  // ★ 연속지적도 ON/OFF 토글
  toggleCadastral(forceState) {
    if (!this.map || !this.cadastralLayer) return;
    this.isCadastralVisible = typeof forceState === 'boolean' ? forceState : !this.isCadastralVisible;

    if (this.isCadastralVisible) {
      if (!this.map.hasLayer(this.cadastralLayer)) {
        this.cadastralLayer.addTo(this.map);
      }
    } else {
      if (this.map.hasLayer(this.cadastralLayer)) {
        this.map.removeLayer(this.cadastralLayer);
      }
    }
    return this.isCadastralVisible;
  }

  // ★ 지도 모드 변경 (일반지도 vs 위성영상+지적도)
  setMapType(type) {
    if (!this.map) return;
    this.currentMapType = type;

    if (type === 'satellite') {
      if (this.map.hasLayer(this.baseLayer)) this.map.removeLayer(this.baseLayer);
      if (!this.map.hasLayer(this.satelliteLayer)) this.satelliteLayer.addTo(this.map);
      if (!this.map.hasLayer(this.hybridLayer)) this.hybridLayer.addTo(this.map);
    } else {
      if (this.map.hasLayer(this.satelliteLayer)) this.map.removeLayer(this.satelliteLayer);
      if (this.map.hasLayer(this.hybridLayer)) this.map.removeLayer(this.hybridLayer);
      if (!this.map.hasLayer(this.baseLayer)) this.baseLayer.addTo(this.map);
    }

    // 연속지적도 레이어가 켜져있으면 최상단 유지
    if (this.isCadastralVisible && !this.map.hasLayer(this.cadastralLayer)) {
      this.cadastralLayer.addTo(this.map);
    }

    // 현재 선택된 필지가 있으면 모드에 맞춰 경계선 스타일 갱신
    if (this.lastParcelCoords) {
      this.updateParcel(this.lastParcelCoords, this.lastParcelTitle, this.lastCenterLat, this.lastCenterLng, false, this.lastParcelInfo);
    }
  }

  showClickMarker(lat, lng) {
    if (!this.map || typeof L === 'undefined') return;
    if (this.markerLayer) this.markerLayer.clearLayers();

    const icon = L.divIcon({
      className: 'custom-map-pin',
      html: `
        <div style="position:relative; width:28px; height:28px; display:flex; align-items:center; justify-content:center;">
          <div style="position:absolute; width:28px; height:28px; border-radius:50%; background:rgba(0,240,255,0.4); animation:ping 1.2s cubic-bezier(0,0,0.2,1) infinite;"></div>
          <div style="width:14px; height:14px; border-radius:50%; background:#00f0ff; border:2px solid #ffffff; box-shadow:0 0 10px #00f0ff;"></div>
        </div>
      `,
      iconSize: [28, 28],
      iconAnchor: [14, 14]
    });

    const marker = L.marker([lat, lng], { icon, interactive: false }).addTo(this.markerLayer);
    this.currentMarker = marker;
  }

  // ★ 다각형 중심점(Centroid) 계산 알고리즘
  calculateCentroid(latlngs) {
    if (!latlngs || latlngs.length === 0) return null;
    let totalLat = 0;
    let totalLng = 0;
    const n = latlngs.length;

    // 슈레이스 공식 기반 면적 가중 중심점 계산
    let x = 0, y = 0, signedArea = 0;
    for (let i = 0; i < n; i++) {
      const p1 = latlngs[i];
      const p2 = latlngs[(i + 1) % n];
      const a = p1[1] * p2[0] - p2[1] * p1[0]; // lng * lat - lng * lat
      signedArea += a;
      x += (p1[1] + p2[1]) * a;
      y += (p1[0] + p2[0]) * a;
    }
    signedArea *= 0.5;

    if (Math.abs(signedArea) > 1e-7) {
      x /= (6 * signedArea);
      y /= (6 * signedArea);
      return [y, x]; // [lat, lng]
    }

    // 대체 평균값
    for (let i = 0; i < n; i++) {
      totalLat += latlngs[i][0];
      totalLng += latlngs[i][1];
    }
    return [totalLat / n, totalLng / n];
  }

  // ★ 지번 텍스트 추출 (필지 안에 지번이 여러개 있어도 정중앙에 1개만 표출 & 지목 '-' 방지)
  extractLotNumber(parcelInfo, title) {
    let jibunStr = "";
    let jimokStr = "";

    const JIMOK_SHORT_MAP = {
      '전': '전', '답': '답', '과': '과', '목': '목', '임': '임',
      '광': '광', '염': '염', '대': '대', '장': '장', '학': '학',
      '차': '차', '주': '주', '창': '창', '도': '도', '철': '철',
      '제': '제', '천': '천', '구': '구', '유': '유', '양': '양',
      '수': '수', '공': '공', '체': '체', '원': '원', '종': '종',
      '사': '사', '묘': '묘', '잡': '잡',
      '대지': '대', '학교용지': '학', '도로': '도', '주차장': '차',
      '공장용지': '장', '하천': '천', '임야': '임', '잡종지': '잡',
      '공원': '공', '체육용지': '체', '종교용지': '종'
    };

    if (parcelInfo) {
      if (parcelInfo.jimok_short && parcelInfo.jimok_short !== '-') {
        jimokStr = parcelInfo.jimok_short;
      } else if (parcelInfo.jimok && parcelInfo.jimok !== '-') {
        const jmMatch = parcelInfo.jimok.match(/\(([가-힣]+)\)/);
        if (jmMatch && jmMatch[1]) {
          jimokStr = jmMatch[1].trim();
        } else {
          const firstHangul = parcelInfo.jimok.match(/[가-힣]/);
          if (firstHangul) jimokStr = firstHangul[0];
        }
      }

      if (parcelInfo.jibun && parcelInfo.jibun !== '-') {
        const cleanNum = parcelInfo.jibun.replace(/[^\d\-]/g, '').trim().replace(/^-+|-+$/g, '');
        if (cleanNum) jibunStr = cleanNum;
        if (!jimokStr || jimokStr === '-') {
          const letterMatch = parcelInfo.jibun.match(/[가-힣]/);
          if (letterMatch) jimokStr = letterMatch[0];
        }
      }

      if (!jibunStr) {
        const addr = parcelInfo.parcel_address || parcelInfo.address || "";
        const match = addr.match(/([가-힣\w]+동|[가-힣\w]+리)?\s*(\d+(?:-\d+)?(?:번지)?)/);
        if (match) {
          jibunStr = (match[1] ? match[1] + " " : "") + match[2].replace("번지", "");
        } else {
          const numMatch = addr.match(/(\d+(?:-\d+)?)/);
          if (numMatch) jibunStr = numMatch[1];
        }
      }
    }

    if (!jibunStr && title) {
      const tMatch = title.match(/(\d+(?:-\d+)?)/);
      if (tMatch) jibunStr = tMatch[1];
    }

    // 지목이 없거나 '-' 또는 공백인 경우 문맥 기반 추정
    if (!jimokStr || jimokStr === '-' || jimokStr.trim() === '') {
      const fullText = (title || '') + ' ' + (parcelInfo ? (parcelInfo.title || '') + ' ' + (parcelInfo.address || '') + ' ' + (parcelInfo.land_use || '') : '');
      if (fullText.includes('학교') || fullText.includes('대학')) {
        jimokStr = '학';
      } else if (fullText.includes('도로')) {
        jimokStr = '도';
      } else if (fullText.includes('주차장')) {
        jimokStr = '차';
      } else if (fullText.includes('공장')) {
        jimokStr = '장';
      } else if (fullText.includes('공원')) {
        jimokStr = '공';
      } else if (fullText.includes('하천')) {
        jimokStr = '천';
      } else {
        jimokStr = '대';
      }
    }

    jimokStr = JIMOK_SHORT_MAP[jimokStr] || jimokStr.substring(0, 1) || '대';

    return {
      jibun: jibunStr || "지번 필지",
      jimok: jimokStr
    };
  }

  // ★ 필지 경계선 및 중앙 단일 지번 배지 렌더링
  updateParcel(polygonCoords, title = "선택된 지적 필지", centerLat, centerLng, shouldPan = false, parcelInfo = null) {
    if (!this.map || typeof L === 'undefined') return;

    this.lastParcelCoords = polygonCoords;
    this.lastParcelTitle = title;
    this.lastCenterLat = centerLat;
    this.lastCenterLng = centerLng;
    this.lastParcelInfo = parcelInfo;

    if (this.polygonLayer) this.polygonLayer.clearLayers();

    if (polygonCoords && polygonCoords.length > 2) {
      const latlngs = polygonCoords.map(pt => [pt[1], pt[0]]);

      // 깔끔하고 자연스러운 단일 필지 외곽선 (기존 스타일로 복귀)
      const polygon = L.polygon(latlngs, {
        color: '#00f0ff',
        weight: 3,
        fillColor: '#0070f3',
        fillOpacity: 0.25,
        dashArray: '4, 4'
      }).addTo(this.polygonLayer);

      // 다각형의 중심점 및 클릭 위치 계산
      const centroid = this.calculateCentroid(latlngs);
      const badgeLat = centerLat || (centroid ? centroid[0] : latlngs[0][0]);
      const badgeLng = centerLng || (centroid ? centroid[1] : latlngs[0][1]);

      // 클릭한 위치 바로 위에 단일 지번 배지 표출
      const lotData = this.extractLotNumber(parcelInfo, title);
      const centerBadgeIcon = L.divIcon({
        className: 'center-jibun-container',
        html: `
          <div class="parcel-center-jibun-badge">
            <span class="jibun-badge-title">${lotData.jibun}</span>
            <span class="jibun-badge-jimok">${lotData.jimok}</span>
          </div>
        `,
        iconSize: [0, 0],
        iconAnchor: [0, 0]
      });

      L.marker([badgeLat, badgeLng], { icon: centerBadgeIcon, interactive: false }).addTo(this.polygonLayer);

      // 마커 및 카메라 뷰 설정
      if (centerLat && centerLng) {
        this.showClickMarker(centerLat, centerLng);
        if (shouldPan) {
          this.map.panTo([centerLat, centerLng], { animate: true, duration: 0.4 });
        }
      } else if (shouldPan) {
        this.map.fitBounds(polygon.getBounds(), { padding: [40, 40], animate: true });
      }
    }
  }

  flyTo(lat, lng, zoom = 18) {
    if (this.map) {
      this.map.setView([lat, lng], zoom, { animate: true, duration: 0.5 });
    }
  }

  resize() {
    if (this.map) {
      this.map.invalidateSize();
    }
  }
}
