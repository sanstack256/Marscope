"use client";

import React, { useEffect, useRef, useState } from "react";
import * as THREE from "three";

export function MarsLandingGlobe() {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const [webglUnavailable, setWebglUnavailable] = useState(false);

  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;

    const prefersReducedMotion =
      typeof window !== "undefined" &&
      window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;

    let renderer: THREE.WebGLRenderer;
    try {
      renderer = new THREE.WebGLRenderer({
        antialias: true,
        alpha: true,
        powerPreference: "high-performance",
      });
    } catch {
      const raf = window.requestAnimationFrame(() => setWebglUnavailable(true));
      return () => window.cancelAnimationFrame(raf);
    }

    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    renderer.setPixelRatio(dpr);
    renderer.toneMapping = THREE.ACESFilmicToneMapping;
    renderer.toneMappingExposure = 1.05;

    const width = container.clientWidth || 520;
    const height = container.clientHeight || 520;
    renderer.setSize(width, height, false);
    renderer.domElement.style.width = "100%";
    renderer.domElement.style.height = "100%";
    renderer.domElement.style.display = "block";
    container.appendChild(renderer.domElement);

    const scene = new THREE.Scene();
    const camera = new THREE.PerspectiveCamera(32, width / height, 0.1, 100);
    camera.position.set(0, 0, 5.15);
    camera.lookAt(0, 0, 0);

    // Realistic solar illumination with natural Martian terminator
    const sunLight = new THREE.DirectionalLight(0xfff7ed, 2.2);
    sunLight.position.set(4.5, 1.8, 3.4);
    scene.add(sunLight);

    const rimFill = new THREE.DirectionalLight(0x6b7280, 0.12);
    rimFill.position.set(-4.0, -1.2, -2.5);
    scene.add(rimFill);

    const ambientLight = new THREE.AmbientLight(0x292320, 0.28);
    scene.add(ambientLight);

    const globeGroup = new THREE.Group();
    globeGroup.rotation.z = THREE.MathUtils.degToRad(14);
    scene.add(globeGroup);

    const textureLoader = new THREE.TextureLoader();
    const marsTexture = textureLoader.load("/landing/mars-globe.jpg");
    marsTexture.colorSpace = THREE.SRGBColorSpace;
    marsTexture.anisotropy = Math.min(4, renderer.capabilities.getMaxAnisotropy());

    const sphereGeom = new THREE.SphereGeometry(1.18, 64, 64);
    const sphereMat = new THREE.MeshStandardMaterial({
      map: marsTexture,
      roughness: 0.92,
      metalness: 0.02,
      bumpMap: marsTexture,
      bumpScale: 0.02,
    });
    const marsMesh = new THREE.Mesh(sphereGeom, sphereMat);
    // Start facing Valles Marineris / Tharsis region
    marsMesh.rotation.y = 2.15;
    globeGroup.add(marsMesh);

    // Pointer & touch damped interaction state
    let pointerActive = false;
    let targetYawOffset = 0;
    let targetPitchOffset = 0;
    let currentYawOffset = 0;
    let currentPitchOffset = 0;
    let idleRotation = marsMesh.rotation.y;

    const updatePointer = (clientX: number, clientY: number) => {
      const rect = container.getBoundingClientRect();
      if (!rect.width || !rect.height) return;
      const nx = ((clientX - rect.left) / rect.width) * 2 - 1;
      const ny = ((clientY - rect.top) / rect.height) * 2 - 1;
      pointerActive = true;
      targetYawOffset = THREE.MathUtils.clamp(nx, -1, 1) * 0.55;
      targetPitchOffset = THREE.MathUtils.clamp(ny, -1, 1) * 0.28;
    };

    const onPointerMove = (e: PointerEvent) => {
      updatePointer(e.clientX, e.clientY);
    };
    const onPointerLeave = () => {
      pointerActive = false;
      targetYawOffset = 0;
      targetPitchOffset = 0;
    };
    const onTouchMove = (e: TouchEvent) => {
      if (e.touches.length > 0) {
        updatePointer(e.touches[0].clientX, e.touches[0].clientY);
      }
    };
    const onTouchEnd = () => {
      pointerActive = false;
      targetYawOffset = 0;
      targetPitchOffset = 0;
    };

    container.addEventListener("pointermove", onPointerMove, { passive: true });
    container.addEventListener("pointerleave", onPointerLeave, { passive: true });
    container.addEventListener("touchmove", onTouchMove, { passive: true });
    container.addEventListener("touchend", onTouchEnd, { passive: true });

    const resizeObserver = new ResizeObserver(() => {
      const w = container.clientWidth;
      const h = container.clientHeight;
      if (w > 0 && h > 0) {
        camera.aspect = w / h;
        camera.updateProjectionMatrix();
        renderer.setSize(w, h, false);
      }
    });
    resizeObserver.observe(container);

    let rafId = 0;
    let lastTime = performance.now();

    const animate = (now: number) => {
      rafId = window.requestAnimationFrame(animate);
      const dt = Math.min(0.05, (now - lastTime) / 1000);
      lastTime = now;

      if (document.hidden) return;

      if (!prefersReducedMotion) {
        const speed = pointerActive ? 0.045 : 0.11;
        idleRotation += dt * speed;
      }

      const damping = 1 - Math.exp(-5.5 * dt);
      currentYawOffset += (targetYawOffset - currentYawOffset) * damping;
      currentPitchOffset += (targetPitchOffset - currentPitchOffset) * damping;

      marsMesh.rotation.y = idleRotation + currentYawOffset;
      globeGroup.rotation.x = currentPitchOffset;

      renderer.render(scene, camera);
    };

    rafId = window.requestAnimationFrame(animate);

    return () => {
      window.cancelAnimationFrame(rafId);
      resizeObserver.disconnect();
      container.removeEventListener("pointermove", onPointerMove);
      container.removeEventListener("pointerleave", onPointerLeave);
      container.removeEventListener("touchmove", onTouchMove);
      container.removeEventListener("touchend", onTouchEnd);

      sphereGeom.dispose();
      sphereMat.dispose();
      marsTexture.dispose();
      renderer.dispose();
      if (renderer.domElement.parentNode === container) {
        container.removeChild(renderer.domElement);
      }
    };
  }, []);

  if (webglUnavailable) {
    return (
      <div className="relative w-full aspect-square max-w-[460px] mx-auto flex items-center justify-center rounded-full border border-[#242424] bg-[#0B0B0B] overflow-hidden">
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img
          src="/landing/mars-globe.jpg"
          alt="Mars MOLA global terrain map"
          className="w-full h-full object-cover opacity-90"
        />
      </div>
    );
  }

  return (
    <div className="relative w-full aspect-square max-w-[460px] mx-auto select-none">
      <div
        ref={containerRef}
        aria-label="Interactive 3D Mars globe"
        className="relative w-full h-full cursor-grab active:cursor-grabbing"
      />
    </div>
  );
}
