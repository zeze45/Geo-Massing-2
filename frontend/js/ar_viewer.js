/**
 * ar_viewer.js - 3D 가상 건축물 & OpenStreetMap 워터마크 없는 2D 지도 연동 (건물-지적도 정밀 축 일치)
 */

class CadastralARViewer {
  constructor(canvasId, videoId) {
    this.canvas = document.getElementById(canvasId);
    this.video = document.getElementById(videoId);
    this.scene = null;
    this.camera = null;
    this.renderer = null;
    this.buildingGroup = new THREE.Group();
    this.groundGroup = new THREE.Group();
    this.mapGroundGroup = new THREE.Group();
    this.hudGroup = new THREE.Group();
    this.currentMode = 'location';
    this.cameraStream = null;
    this.currentMassingData = null;
    this.currentLegalMetrics = null;

    this.isDragging = false;
    this.previousMousePosition = { x: 0, y: 0 };
    this.rotationY = 0.5;
    this.rotationX = 0.45;
    this.targetZoom = 38;
    this.lookAtHeight = 5;
    this.initialPinchDistance = 0;
    this.currentLat = 37.448919;
    this.currentLng = 127.167702;
    this.userRotationDeg = 0;
    this.userScaleX = 1.0;
    this.userScaleZ = 1.0;
    this.lastTileRedraw = null;
    this.detectedBuildingAngle = 0;
    this.floorBadges = [];
    this._tmpVec = new THREE.Vector3();
    this.panOffset = new THREE.Vector3(0, 0, 0);
    this.prevTouchMid = null;
    this.isPanning = false;
  }

  init() {
    if (typeof THREE === 'undefined') {
      console.error("Three.js not loaded");
      return;
    }

    const width = Math.max(window.innerWidth, this.canvas.clientWidth || 360);
    const height = Math.max(window.innerHeight - 150, this.canvas.clientHeight || 480);

    // 1. Scene & Camera (초고층 랜드마크까지 조망 가능한 5000m far plane)
    this.scene = new THREE.Scene();
    this.camera = new THREE.PerspectiveCamera(48, width / height, 0.1, 5000);
    this.camera.position.set(18, 22, 32);
    this.camera.lookAt(0, 5, 0);

    // 2. Renderer
    this.renderer = new THREE.WebGLRenderer({
      canvas: this.canvas,
      alpha: true,
      antialias: true,
      powerPreference: 'high-performance'
    });
    this.renderer.setSize(width, height);
    this.renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));

    // 3. 조명 (과노출 방지 및 선명한 3D 입체감)
    const ambientLight = new THREE.AmbientLight(0xffffff, 0.9);
    this.scene.add(ambientLight);

    const dirLight1 = new THREE.DirectionalLight(0x00f0ff, 1.0);
    dirLight1.position.set(30, 50, 30);
    this.scene.add(dirLight1);

    const dirLight2 = new THREE.DirectionalLight(0x0070f3, 0.8);
    dirLight2.position.set(-30, 30, -30);
    this.scene.add(dirLight2);

    const pointLight = new THREE.PointLight(0x00ff88, 1.2, 90);
    pointLight.position.set(0, 15, 0);
    this.scene.add(pointLight);

    // 4. 그룹 등록
    this.scene.add(this.mapGroundGroup);
    this.scene.add(this.buildingGroup);
    this.scene.add(this.hudGroup);

    // 5. 초기 2D 지도 바닥 생성 (신구대학교 본관 좌표)
    this.update3DCadastralGround({ width_m: 60, depth_m: 50, site_area_sqm: 3000 }, null, null, 37.448919, 127.167702);

    // 6. 이벤트 바인딩
    this.bindEvents();

    // 7. 렌더 루프
    this.animate();
  }

  setMode(mode) {
    this.currentMode = mode;
    const arControls = document.getElementById('camera-ar-controls');

    if (mode === 'camera_ar') {
      this.mapGroundGroup.visible = false;
      if (arControls) arControls.classList.remove('hidden');
      this.startCamera();
    } else {
      if (arControls) arControls.classList.add('hidden');
      this.stopCamera();
      this.mapGroundGroup.visible = true;
    }
  }

  async startCamera() {
    try {
      if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
        throw new Error("HTTPS 연결 필요");
      }

      const stream = await navigator.mediaDevices.getUserMedia({
        video: {
          facingMode: { ideal: 'environment' },
          width: { ideal: 1280 },
          height: { ideal: 720 }
        },
        audio: false
      });

      this.cameraStream = stream;
      this.video.srcObject = stream;
      this.video.setAttribute('playsinline', 'true');
      await this.video.play();
      this.video.style.display = 'block';
      return true;
    } catch (err) {
      console.warn("Camera start error:", err);
      this.video.style.display = 'none';
      return false;
    }
  }

  stopCamera() {
    if (this.cameraStream) {
      this.cameraStream.getTracks().forEach(track => track.stop());
      this.cameraStream = null;
    }
    this.video.style.display = 'none';
  }

  updateMassing(massingData, legalMetrics, lat = 37.448919, lng = 127.167702) {
    this.currentMassingData = massingData;
    this.currentLegalMetrics = legalMetrics;

    const bld = massingData?.massing_building;
    const site = massingData?.site_geometry;
    const floorLayers = bld?.floor_layers || [];

    // 대지/건물 지오메트리 중심점(center_geo)을 바닥 지도 타일 중심과 1:1로 정밀 일치
    const centerLat = (site && site.center_geo && site.center_geo.lat) ? site.center_geo.lat : lat;
    const centerLng = (site && site.center_geo && site.center_geo.lng) ? site.center_geo.lng : lng;

    this.currentLat = centerLat;
    this.currentLng = centerLng;
    this.buildingGroup.clear();
    this.hudGroup.clear();
    this.floorBadges = [];

    if (!massingData || !massingData.massing_building) return;

    // ★ 1. 국토교통부 V-World 공공 타일 지도 3D 바닥 연동 (중심점 1:1 완벽 정렬)
    this.update3DCadastralGround(site, massingData, legalMetrics, centerLat, centerLng);

    // 대지 바닥의 파란색 넓은 사각형 제거 (실제 지도 타일 본연의 발색 유지)

    // ★ 3. 층별 3D 매싱 볼륨 (지적 폴리곤의 형상·회전각과 100% 일치하는 ExtrudeGeometry 적용)
    floorLayers.forEach((layer) => {
      const h = layer.height_m || 3.2;
      const elev = layer.elevation_bottom_m;
      const poly = (layer.polygon && layer.polygon.length >= 3) ? layer.polygon : (site ? site.meter_polygon : null);

      if (poly) {
        // 다각형 정점 Winding Order를 항상 반시계방향(CCW)으로 정규화 (Three.js Earcut 삼각화 100% 정합성)
        let shapePts = poly.map(pt => ({ x: pt.x, y: -pt.z }));
        let signedArea = 0;
        for (let i = 0; i < shapePts.length; i++) {
          const j = (i + 1) % shapePts.length;
          signedArea += (shapePts[i].x * shapePts[j].y - shapePts[j].x * shapePts[i].y);
        }
        if (signedArea < 0) {
          shapePts.reverse();
        }

        // 대지 폴리곤 각도와 일치하는 건물 층별 2D Shape
        const floorShape = new THREE.Shape();
        shapePts.forEach((pt, idx) => {
          if (idx === 0) floorShape.moveTo(pt.x, pt.y);
          else floorShape.lineTo(pt.x, pt.y);
        });
        floorShape.closePath();

        // 오목 다각형 및 복잡 다각형에서 정점 찢어짐(Artifact)을 방지하기 위해 bevelEnabled: false 적용
        const extrudeSettings = {
          depth: Math.max(0.5, h - 0.08),
          bevelEnabled: false
        };
        const floorGeom = new THREE.ExtrudeGeometry(floorShape, extrudeSettings);
        floorGeom.rotateX(-Math.PI / 2);

        const glassMat = new THREE.MeshStandardMaterial({
          color: 0x00b4d8,
          transparent: true,
          opacity: 0.72,
          roughness: 0.15,
          metalness: 0.45,
          side: THREE.DoubleSide
        });
        const floorMesh = new THREE.Mesh(floorGeom, glassMat);
        floorMesh.position.set(0, elev, 0);
        this.buildingGroup.add(floorMesh);

        // 층별 모서리 와이어프레임
        const edges = new THREE.EdgesGeometry(floorGeom);
        const lineMat = new THREE.LineBasicMaterial({
          color: layer.north_setback_m > 0 ? 0xffb700 : 0x00ffff,
          linewidth: 2
        });
        const edgeLines = new THREE.LineSegments(edges, lineMat);
        edgeLines.position.set(0, elev, 0);
        this.buildingGroup.add(edgeLines);

        // 층간 슬래브 (두께 0.12m)
        const slabGeom = new THREE.ExtrudeGeometry(floorShape, {
          depth: 0.12,
          bevelEnabled: false
        });
        slabGeom.rotateX(-Math.PI / 2);
        const slabMat = new THREE.MeshStandardMaterial({
          color: 0x023e8a,
          roughness: 0.4,
          metalness: 0.7
        });
        const slabMesh = new THREE.Mesh(slabGeom, slabMat);
        slabMesh.position.set(0, elev, 0);
        // 층수 표시 3D 뱃지 (초고층 건물 뷰포트 오버플로우 방지 스마트 인터벌)
        const totalFloors = bld.floors_count || floorLayers.length;
        let shouldShowBadge = false;
        if (totalFloors <= 15) {
          shouldShowBadge = true;
        } else if (totalFloors <= 40) {
          shouldShowBadge = (layer.floor_number === 1 || layer.floor_number % 5 === 0 || layer.floor_number === totalFloors);
        } else {
          shouldShowBadge = (layer.floor_number === 1 || layer.floor_number % 10 === 0 || layer.floor_number === totalFloors);
        }

        if (shouldShowBadge) {
          // 건물 꼭짓점 바깥쪽으로 오프셋 배치하여 건물 벽에 묻히지 않도록 공간 확보
          const badgeVertex = poly[0] || { x: 5, z: 5 };
          const len = Math.hypot(badgeVertex.x, badgeVertex.z) || 1.0;
          const offsetDist = Math.max(1.2, Math.min(2.8, len * 0.14));
          const offsetX = badgeVertex.x + (badgeVertex.x / len) * offsetDist;
          const offsetZ = badgeVertex.z + (badgeVertex.z / len) * offsetDist;
          const isTop = (layer.floor_number === totalFloors);
          this.createFloorBadge(layer.floor_number, elev + (h * 0.5), offsetX, offsetZ, isTop, totalFloors, h);
        }
      }
    });

    // 초고층 랜드마크(123층 등) 및 초대형 건물(킨텍스 등)도 한눈에 웅장하게 프레이밍되도록 카메라 거리 및 시점 높이 동적 계산
    const maxDim = Math.max(bld.width_m || 30, bld.depth_m || 30);
    const height = bld.total_height_m || 15;
    let fitDist;
    if (maxDim >= 200) {
      fitDist = Math.max(maxDim * 1.35, height * 2.2, 80);
    } else {
      fitDist = Math.max(maxDim * 2.2, height * 1.65, 40);
    }
    this.targetZoom = THREE.MathUtils.clamp(fitDist, 35, 1600);
    this.lookAtHeight = Math.min(height * 0.45, 270);
    // 건물 및 대지 그룹에 회전 및 스케일 적용
    this.buildingGroup.rotation.y = THREE.MathUtils.degToRad(this.userRotationDeg || 0);
    this.buildingGroup.scale.set(this.userScaleX || 1.0, 1.0, this.userScaleZ || 1.0);
  }

  // ★ 3D 건물 바닥에 국토교통부 V-World WMTS 지적도 2D 타일 매핑 & 서브미터 정밀 정렬 (대형 부지 5x5 확장)
  update3DCadastralGround(site, massingData, legalMetrics, lat = 37.448919, lng = 127.167702) {
    this.mapGroundGroup.clear();

    const zoom = 18;
    const n = Math.pow(2, zoom);
    const rad = lat * Math.PI / 180;
    const exactX = (lng + 180) / 360 * n;
    const exactY = (1 - Math.log(Math.tan(rad) + 1 / Math.cos(rad)) / Math.PI) / 2 * n;
    const tileX = Math.floor(exactX);
    const tileY = Math.floor(exactY);

    // 해당 위도에서의 1 타일 물리적 미터 크기 및 서브타일 미터 오프셋 연산
    const w_tile = (40075016.686 * Math.cos(rad)) / n;

    // 대형 랜드마크(킨텍스, 대학교 등 250m 초과)인 경우 5x5 타일(약 600m)로 확장
    const siteMaxDim = (site && (site.width_m || site.depth_m)) ? Math.max(site.width_m || 0, site.depth_m || 0) : 30;
    const isLarge = siteMaxDim >= 250;
    const gridDim = isLarge ? 5 : 3;
    const halfG = Math.floor(gridDim / 2);
    const canvasPx = 256 * gridDim;
    const centerPx = (canvasPx / 2);

    const px = (exactX - tileX) * 256;
    const py = (exactY - tileY) * 256;
    const cx = (halfG * 256) + px;
    const cy = (halfG * 256) + py;
    const dx = (cx - centerPx) * (w_tile / 256);
    const dz = (cy - centerPx) * (w_tile / 256);

    const canvas = document.createElement('canvas');
    canvas.width = canvasPx;
    canvas.height = canvasPx;
    const ctx = canvas.getContext('2d');

    // 1. 기본 사이버 다크 지적 베이스
    ctx.fillStyle = '#0a1124';
    ctx.fillRect(0, 0, canvasPx, canvasPx);

    // 격자 그리드 그리기 (지적도 감성)
    ctx.strokeStyle = 'rgba(0, 240, 255, 0.08)';
    ctx.lineWidth = 1;
    for (let i = 0; i <= canvasPx; i += 64) {
      ctx.beginPath();
      ctx.moveTo(i, 0);
      ctx.lineTo(i, canvasPx);
      ctx.stroke();
      ctx.beginPath();
      ctx.moveTo(0, i);
      ctx.lineTo(canvasPx, i);
      ctx.stroke();
    }

    const texture = new THREE.CanvasTexture(canvas);
    texture.minFilter = THREE.LinearFilter;
    texture.magFilter = THREE.LinearFilter;
    texture.needsUpdate = true;

    // 조명 과노출(Whiteout) 방지를 위해 MeshBasicMaterial 사용 (100% 또렷한 원본 타일 발색)
    const groundGeom = new THREE.PlaneGeometry(gridDim * w_tile, gridDim * w_tile);
    const groundMat = new THREE.MeshBasicMaterial({
      map: texture,
      side: THREE.DoubleSide
    });

    const groundMesh = new THREE.Mesh(groundGeom, groundMat);
    groundMesh.rotateX(-Math.PI / 2);
    groundMesh.position.set(-dx, 0, -dz);
    this.mapGroundGroup.add(groundMesh);

    // 2. 지적도 타일 이미지 렌더링 완료 후 대지 경계 오버레이 합성 함수 (사용자 회전각 100% 동기화)
    const drawCadastralOverlay = () => {
      if (site && site.meter_polygon && site.meter_polygon.length >= 3) {
        const m2px = 256 / w_tile;
        const rad_u = THREE.MathUtils.degToRad(this.userRotationDeg || 0);
        const cos_u = Math.cos(rad_u);
        const sin_u = Math.sin(rad_u);
        const sx = this.userScaleX || 1.0;
        const sz = this.userScaleZ || 1.0;
        
        ctx.save();
        // 실제 대지 폴리곤 패스 생성 (3D 모델링 회전각과 100% 일치)
        ctx.beginPath();
        site.meter_polygon.forEach((pt, idx) => {
          const scaledX = pt.x * sx;
          const scaledZ = pt.z * sz;
          const rx = scaledX * cos_u + scaledZ * sin_u;
          const rz = -scaledX * sin_u + scaledZ * cos_u;
          const px_pos = cx + rx * m2px;
          const py_pos = cy + rz * m2px;
          if (idx === 0) ctx.moveTo(px_pos, py_pos);
          else ctx.lineTo(px_pos, py_pos);
        });
        ctx.closePath();

        // 정북(N) 방향 인디케이터 (우측 상단)
        ctx.fillStyle = 'rgba(15, 23, 42, 0.8)';
        ctx.beginPath();
        ctx.arc(canvasPx - 48, 48, 22, 0, Math.PI * 2);
        ctx.fill();
        ctx.strokeStyle = '#38bdf8';
        ctx.lineWidth = 1.5;
        ctx.stroke();

        ctx.fillStyle = '#f43f5e';
        ctx.font = 'bold 13px sans-serif';
        ctx.fillText('▲ N', canvasPx - 48, 48);

        ctx.restore();
      }
      texture.needsUpdate = true;
    };

    this.lastTileRedraw = drawCadastralOverlay;

    let loadedCount = 0;
    const totalTiles = gridDim * gridDim;
    const vworldKey = window.vworldApiKey || "DEB860E4-52DC-35F3-9E68-664B22DF3592";

    // 3. Grid 타일 로드 (국토교통부 V-World WMTS 타일)
    for (let dy = -halfG; dy <= halfG; dy++) {
      for (let dx_t = -halfG; dx_t <= halfG; dx_t++) {
        const currentX = tileX + dx_t;
        const currentY = tileY + dy;
        const posX = (dx_t + halfG) * 256;
        const posY = (dy + halfG) * 256;

        const img = new Image();
        img.crossOrigin = 'Anonymous';
        img.onload = () => {
          ctx.drawImage(img, posX, posY, 256, 256);
          loadedCount++;
          if (loadedCount === totalTiles) {
            drawCadastralOverlay();
          } else {
            texture.needsUpdate = true;
          }
        };
        img.onerror = () => {
          // V-World 네트워크 장애 시 고화질 스트리트맵 자동 폴백
          const fallback = new Image();
          fallback.crossOrigin = 'Anonymous';
          fallback.onload = () => {
            ctx.drawImage(fallback, posX, posY, 256, 256);
            loadedCount++;
            if (loadedCount === totalTiles) {
              drawCadastralOverlay();
            } else {
              texture.needsUpdate = true;
            }
          };
          fallback.onerror = () => {
            ctx.fillStyle = '#0f172a';
            ctx.fillRect(posX, posY, 256, 256);
            loadedCount++;
            if (loadedCount === totalTiles) {
              drawCadastralOverlay();
            } else {
              texture.needsUpdate = true;
            }
          };
          fallback.src = `https://server.arcgisonline.com/ArcGIS/rest/services/World_Street_Map/MapServer/tile/${zoom}/${currentY}/${currentX}`;
        };

        // 국토교통부 V-World 공식 WMTS Base 타일
        img.src = `https://api.vworld.kr/req/wmts/1.0.0/${vworldKey}/Base/${zoom}/${currentY}/${currentX}.png`;
      }
    }

    drawCadastralOverlay();
  }

  // ★ 3D 모델링 회전 & 지도 정밀 정렬 컨트롤 API
  setBuildingRotation(degrees, updateOverlay = true) {
    this.userRotationDeg = Number(degrees) || 0;
    if (this.buildingGroup) {
      this.buildingGroup.rotation.y = THREE.MathUtils.degToRad(this.userRotationDeg);
    }
    if (updateOverlay && this.lastTileRedraw) {
      this.lastTileRedraw();
    }
    const valEl = document.getElementById('building-rot-val');
    if (valEl) valEl.textContent = `${this.userRotationDeg >= 0 ? '+' : ''}${this.userRotationDeg.toFixed(1)}°`;
    const sliderEl = document.getElementById('building-rot-slider');
    if (sliderEl) sliderEl.value = this.userRotationDeg;
  }

  rotateBuildingRelative(deltaDeg) {
    let newDeg = (this.userRotationDeg || 0) + deltaDeg;
    while (newDeg > 180) newDeg -= 360;
    while (newDeg < -180) newDeg += 360;
    this.setBuildingRotation(newDeg);
  }

  setBuildingAspectPreset(preset) {
    if (preset === 'square') {
      this.userScaleX = 1.0;
      this.userScaleZ = 1.0;
    } else if (preset === 'wide') {
      this.userScaleX = 1.25;
      this.userScaleZ = 0.85;
    } else if (preset === 'deep') {
      this.userScaleX = 0.85;
      this.userScaleZ = 1.25;
    } else {
      this.userScaleX = 1.0;
      this.userScaleZ = 1.0;
    }
    if (this.buildingGroup) {
      this.buildingGroup.scale.set(this.userScaleX, 1.0, this.userScaleZ);
    }
    if (this.lastTileRedraw) {
      this.lastTileRedraw();
    }
  }

  resetBuildingAlignment() {
    this.setBuildingRotation(0);
    this.setBuildingAspectPreset('square');
  }

  createFloorBadge(floorNum, y, x, z, isTop = false, totalFloors = 10, floorHeight = 3.2) {
    const canvas = document.createElement('canvas');
    canvas.width = 180;
    canvas.height = 64;
    const ctx = canvas.getContext('2d');

    // 둥근 모서리 사각형 배경 (세련된 라운드 HUD 배지)
    const rw = 174, rh = 58, rx = 3, ry = 3, r = 12;
    ctx.beginPath();
    ctx.moveTo(rx + r, ry);
    ctx.lineTo(rx + rw - r, ry);
    ctx.quadraticCurveTo(rx + rw, ry, rx + rw, ry + r);
    ctx.lineTo(rx + rw, ry + rh - r);
    ctx.quadraticCurveTo(rx + rw, ry + rh, rx + rw - r, ry + rh);
    ctx.lineTo(rx + r, ry + rh);
    ctx.quadraticCurveTo(rx, ry + rh, rx, ry + rh - r);
    ctx.lineTo(rx, ry + r);
    ctx.quadraticCurveTo(rx, ry, rx + r, ry);
    ctx.closePath();

    if (isTop) {
      // 최상층 프리미엄 골드/에메랄드 시그니처 배지
      const grad = ctx.createLinearGradient(0, 0, 180, 64);
      grad.addColorStop(0, 'rgba(6, 40, 30, 0.94)');
      grad.addColorStop(1, 'rgba(10, 60, 45, 0.96)');
      ctx.fillStyle = grad;
      ctx.fill();

      ctx.strokeStyle = '#10b981';
      ctx.lineWidth = 3;
      ctx.shadowColor = '#10b981';
      ctx.shadowBlur = 8;
      ctx.stroke();
      ctx.shadowBlur = 0;

      ctx.fillStyle = '#34d399';
      ctx.font = 'bold 28px Rajdhani, Pretendard, sans-serif';
      ctx.textAlign = 'center';
      ctx.textBaseline = 'middle';
      ctx.fillText(`${floorNum}F TOP`, 90, 32);
    } else {
      // 일반층 현대적 네온 사이언 글래스모피즘 배지
      const grad = ctx.createLinearGradient(0, 0, 180, 64);
      grad.addColorStop(0, 'rgba(6, 15, 30, 0.90)');
      grad.addColorStop(1, 'rgba(12, 28, 55, 0.92)');
      ctx.fillStyle = grad;
      ctx.fill();

      ctx.strokeStyle = '#00f0ff';
      ctx.lineWidth = 2.5;
      ctx.shadowColor = '#00f0ff';
      ctx.shadowBlur = 6;
      ctx.stroke();
      ctx.shadowBlur = 0;

      ctx.fillStyle = '#00f0ff';
      ctx.font = 'bold 30px Rajdhani, Pretendard, sans-serif';
      ctx.textAlign = 'center';
      ctx.textBaseline = 'middle';
      ctx.fillText(`${floorNum}F`, 90, 32);
    }

    const texture = new THREE.CanvasTexture(canvas);
    texture.minFilter = THREE.LinearFilter;
    texture.needsUpdate = true;

    // ★ depthTest: false & renderOrder: 999 -> 건물 모델링에 묻히지 않고 항상 최상단에 또렷하게 표시
    const badgeMat = new THREE.SpriteMaterial({
      map: texture,
      transparent: true,
      depthTest: false,
      depthWrite: false
    });
    const sprite = new THREE.Sprite(badgeMat);
    sprite.renderOrder = 999;
    sprite.position.set(x, y, z);

    // 초기 스케일 설정 (작은 건물에서도 슬림하고 단정하게 유지)
    const initH = Math.min(2.0, Math.max(1.0, floorHeight * 0.55));
    sprite.scale.set(initH * 2.6, initH, 1);

    this.buildingGroup.add(sprite);

    // 줌인/줌아웃 시 실시간 반응형 동적 스케일링을 위해 목록 등록
    this.floorBadges.push({
      sprite,
      floorHeight,
      floorNum,
      isTop
    });
  }

  resetView() {
    this.rotationY = 0.5;
    this.rotationX = 0.45;
    this.panOffset.set(0, 0, 0);
    const bld = this.currentMassingData?.building || {};
    const maxDim = Math.max(bld.width_m || 30, bld.depth_m || 30);
    const height = bld.total_height_m || 15;
    const fitDist = maxDim >= 200 ? Math.max(maxDim * 1.35, height * 2.2, 80) : Math.max(maxDim * 2.2, height * 1.65, 40);
    this.targetZoom = THREE.MathUtils.clamp(fitDist, 38, 1400);
    this.lookAtHeight = Math.min(height * 0.45, 270);
  }

  // ★ 모바일 2손가락 슬라이드 & 마우스 화면 이동(Pan) 함수
  // 화면을 부드럽고 안정적으로 이동할 수 있도록 감도 조절
  pan(deltaX, deltaY) {
    const panFactor = Math.max(0.035, this.targetZoom * 0.0028);

    const sinY = Math.sin(this.rotationY);
    const cosY = Math.cos(this.rotationY);
    const sinX = Math.sin(this.rotationX);
    const cosX = Math.cos(this.rotationX);

    // 스크린 로컬 수평/수직 축을 3D 월드 좌표계로 매핑
    const rightX = cosY;
    const rightZ = -sinY;

    const upX = -sinY * sinX;
    const upY = cosX;
    const upZ = -cosY * sinX;

    // 상하 반전(Invert Y): deltaY 부호 반전 적용
    const invDeltaY = -deltaY;
    this.panOffset.x -= (rightX * deltaX - upX * invDeltaY) * panFactor;
    this.panOffset.y -= upY * invDeltaY * panFactor;
    this.panOffset.z -= (rightZ * deltaX - upZ * invDeltaY) * panFactor;
  }

  bindEvents() {
    window.addEventListener('resize', () => this.onWindowResize());

    // 마우스 이벤트 (좌클릭: 3D 회전, 우클릭/Shift클릭: 화면 이동 Pan)
    this.canvas.addEventListener('mousedown', (e) => {
      if (e.button === 2 || e.shiftKey) {
        this.isPanning = true;
        this.previousMousePosition = { x: e.clientX, y: e.clientY };
      } else if (e.button === 0) {
        this.onPointerDown(e.clientX, e.clientY);
      }
    });

    window.addEventListener('mousemove', (e) => {
      if (this.isPanning) {
        const dx = e.clientX - this.previousMousePosition.x;
        const dy = e.clientY - this.previousMousePosition.y;
        this.pan(dx, dy);
        this.previousMousePosition = { x: e.clientX, y: e.clientY };
      } else {
        this.onPointerMove(e.clientX, e.clientY);
      }
    });

    window.addEventListener('mouseup', () => {
      this.isPanning = false;
      this.onPointerUp();
    });

    this.canvas.addEventListener('contextmenu', (e) => e.preventDefault());

    // 터치 이벤트 (1손가락: 3D 회전, 2손가락 동시 슬라이드: 화면 이동 Pan, 2손가락 벌리기/오므리기: 줌)
    this.canvas.addEventListener('touchstart', (e) => {
      if (e.touches.length === 1) {
        this.onPointerDown(e.touches[0].clientX, e.touches[0].clientY);
      } else if (e.touches.length === 2) {
        this.isDragging = false;
        const x0 = e.touches[0].clientX;
        const y0 = e.touches[0].clientY;
        const x1 = e.touches[1].clientX;
        const y1 = e.touches[1].clientY;
        const dx = x0 - x1;
        const dy = y0 - y1;
        this.initialPinchDistance = Math.hypot(dx, dy);
        this.initialZoom = this.targetZoom;
        this.prevTouchMid = { x: (x0 + x1) * 0.5, y: (y0 + y1) * 0.5 };
      }
    }, { passive: true });

    this.canvas.addEventListener('touchmove', (e) => {
      if (e.touches.length === 1 && this.isDragging) {
        this.onPointerMove(e.touches[0].clientX, e.touches[0].clientY);
      } else if (e.touches.length === 2) {
        const x0 = e.touches[0].clientX;
        const y0 = e.touches[0].clientY;
        const x1 = e.touches[1].clientX;
        const y1 = e.touches[1].clientY;

        const curMidX = (x0 + x1) * 0.5;
        const curMidY = (y0 + y1) * 0.5;

        // ★ 1. 두 손가락 같은 방향 슬라이드 -> 화면 이동 (Pan) 속도 완화 감도 적용
        if (this.prevTouchMid) {
          const touchPanDamping = 0.5; // 터치 시 화면이 너무 빠르게 튀지 않도록 감도 완화
          const deltaMidX = (curMidX - this.prevTouchMid.x) * touchPanDamping;
          const deltaMidY = (curMidY - this.prevTouchMid.y) * touchPanDamping;
          this.pan(deltaMidX, deltaMidY);
        }
        this.prevTouchMid = { x: curMidX, y: curMidY };

        // ★ 2. 두 손가락 간격 변화 -> 줌 (Pinch Zoom)
        if (this.initialPinchDistance > 0) {
          const currentDistance = Math.hypot(x0 - x1, y0 - y1);
          if (currentDistance > 10) {
            const factor = this.initialPinchDistance / currentDistance;
            this.targetZoom = THREE.MathUtils.clamp(this.initialZoom * factor, 15, 2000);
          }
        }
      }
    }, { passive: true });

    this.canvas.addEventListener('touchend', () => {
      this.isDragging = false;
      this.initialPinchDistance = 0;
      this.prevTouchMid = null;
    });

    this.canvas.addEventListener('wheel', (e) => {
      e.preventDefault();
      this.targetZoom += e.deltaY * 0.25;
      this.targetZoom = THREE.MathUtils.clamp(this.targetZoom, 15, 2000);
    }, { passive: false });
  }

  onPointerDown(x, y) {
    this.isDragging = true;
    this.previousMousePosition = { x, y };
  }

  onPointerMove(x, y) {
    if (!this.isDragging) return;

    const deltaX = x - this.previousMousePosition.x;
    const deltaY = y - this.previousMousePosition.y;

    // 3D 회전 제어 (좌우 회전 및 상하 회전 반전)
    this.rotationY -= deltaX * 0.008;
    this.rotationX += deltaY * 0.005; // 상하 회전 반전 적용
    this.rotationX = THREE.MathUtils.clamp(this.rotationX, 0.1, 1.45);

    this.previousMousePosition = { x, y };
  }

  onPointerUp() {
    this.isDragging = false;
  }

  onWindowResize() {
    if (!this.canvas || !this.renderer || !this.camera) return;

    const width = Math.max(window.innerWidth, this.canvas.clientWidth || 360);
    const height = Math.max(window.innerHeight - 150, this.canvas.clientHeight || 480);

    this.camera.aspect = width / height;
    this.camera.updateProjectionMatrix();
    this.renderer.setSize(width, height);
  }

  animate() {
    this.animationId = requestAnimationFrame(() => this.animate());

    if (this.camera) {
      const radius = this.targetZoom;
      const targetX = this.panOffset.x;
      const targetY = (this.lookAtHeight || 5) + this.panOffset.y;
      const targetZ = this.panOffset.z;

      this.camera.position.x = targetX + radius * Math.sin(this.rotationY) * Math.cos(this.rotationX);
      this.camera.position.z = targetZ + radius * Math.cos(this.rotationY) * Math.cos(this.rotationX);
      this.camera.position.y = targetY + radius * Math.sin(this.rotationX);
      this.camera.lookAt(targetX, targetY, targetZ);

      // ★ 줌인/줌아웃 시 층 표시 뱃지 크기 실시간 동적 스케일링 (화면 가독성 및 비율 최적화)
      if (this.floorBadges && this.floorBadges.length > 0) {
        const camPos = this.camera.position;
        for (const item of this.floorBadges) {
          if (!item.sprite || !item.sprite.parent) continue;
          item.sprite.getWorldPosition(this._tmpVec);
          const dist = camPos.distanceTo(this._tmpVec);
          const fh = item.floorHeight || 3.2;

          // 거리에 부드럽게 비례하되 급격한 팽창/수축을 방지하는 스마트 스케일링
          // 줌인(가까움): 아담하고 정밀하게 축소되어 건물을 가리지 않음
          // 줌아웃(멀어짐): 과도하게 작아지지 않고 또렷하게 식별됨
          const distFactor = THREE.MathUtils.clamp(dist * 0.042, 0.7, 12.0);
          const badgeH = THREE.MathUtils.clamp(distFactor * 0.55, 0.75, Math.max(2.0, fh * 0.75));
          const badgeW = badgeH * 2.6;
          item.sprite.scale.set(badgeW, badgeH, 1.0);
        }
      }
    }

    if (this.renderer && this.scene && this.camera) {
      this.renderer.render(this.scene, this.camera);
    }
  }
}
