/**
 * map.js - Leaflet 기반 지적도 및 공간정보 지도 뷰어 (클릭으로 건물 선택 & 3D 연동)
 */

class CadastralMap {
  constructor(mapContainerId, onParcelSelect) {
    this.containerId = mapContainerId;
    this.onParcelSelect = onParcelSelect;
    this.map = null;
    this.polygonLayer = null;
    this.markerLayer = null;
    this.currentMarker = null;
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
      attributionControl: false
    }).setView([defaultLat, defaultLng], zoom);

    L.control.zoom({ position: 'bottomright' }).addTo(this.map);

    const vworldKey = window.vworldApiKey || "DEB860E4-52DC-35F3-9E68-664B22DF3592";
    L.tileLayer(`https://api.vworld.kr/req/wmts/1.0.0/${vworldKey}/Base/{z}/{y}/{x}.png`, {
      maxZoom: 19,
      errorTileUrl: 'https://server.arcgisonline.com/ArcGIS/rest/services/World_Street_Map/MapServer/tile/{z}/{y}/{x}'
    }).addTo(this.map);

    this.polygonLayer = L.layerGroup().addTo(this.map);
    this.markerLayer = L.layerGroup().addTo(this.map);

    // 지도 클릭 시 해당 위치의 건물/필지 선택
    this.map.on('click', (e) => {
      const { lat, lng } = e.latlng;
      this.showClickMarker(lat, lng);
      if (this.onParcelSelect) {
        this.onParcelSelect(lat, lng);
      }
    });

    setTimeout(() => {
      if (this.map) this.map.invalidateSize();
    }, 200);
  }

  showClickMarker(lat, lng, title = "📍 건물 선택됨", subtitle = "AI 3D 모델링 & 건축 법규 로딩 중...") {
    if (!this.map || typeof L === 'undefined') return;
    if (this.markerLayer) this.markerLayer.clearLayers();

    // 네온 사이언 펄스 마커
    const icon = L.divIcon({
      className: 'custom-map-pin',
      html: `
        <div style="position:relative; width:28px; height:28px; display:flex; align-items:center; justify-content:center;">
          <div style="position:absolute; width:28px; height:28px; border-radius:50%; background:rgba(0,240,255,0.4); animation:ping 1s cubic-bezier(0,0,0.2,1) infinite;"></div>
          <div style="width:14px; height:14px; border-radius:50%; background:#00f0ff; border:2px solid #ffffff; box-shadow:0 0 10px #00f0ff;"></div>
        </div>
      `,
      iconSize: [28, 28],
      iconAnchor: [14, 14]
    });

    const marker = L.marker([lat, lng], { icon }).addTo(this.markerLayer);
    marker.bindPopup(`
      <div style="font-family:sans-serif; text-align:center; padding:4px 6px;">
        <b style="color:#00f0ff; font-size:12px;">${title}</b><br/>
        <span style="font-size:11px; color:#94a3b8;">${subtitle}</span>
      </div>
    `).openPopup();
    this.currentMarker = marker;
  }

  updateParcel(polygonCoords, title = "선택된 지적 필지", centerLat, centerLng) {
    if (!this.map || typeof L === 'undefined') return;

    if (this.polygonLayer) this.polygonLayer.clearLayers();

    if (polygonCoords && polygonCoords.length > 2) {
      const latlngs = polygonCoords.map(pt => [pt[1], pt[0]]);
      
      const polygon = L.polygon(latlngs, {
        color: '#00f0ff',
        weight: 3,
        fillColor: '#0070f3',
        fillOpacity: 0.35,
        dashArray: '4, 4'
      }).addTo(this.polygonLayer);

      if (centerLat && centerLng) {
        // ★ 공식 중심 좌표로 마커 스냅 및 지도 포커스 이동
        this.showClickMarker(centerLat, centerLng, title, '공식 지적 & 건물 정밀 위치 스냅 완료');
        this.map.panTo([centerLat, centerLng], { animate: true, duration: 0.4 });
      } else {
        this.map.fitBounds(polygon.getBounds(), { padding: [40, 40], animate: true });
      }
    }
  }

  resize() {
    if (this.map) {
      this.map.invalidateSize();
    }
  }
}
