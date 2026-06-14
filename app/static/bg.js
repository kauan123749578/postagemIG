(function () {
  const canvas = document.createElement("canvas");
  canvas.id = "gpu-bg";
  canvas.setAttribute("aria-hidden", "true");
  document.body.prepend(canvas);

  const ctx = canvas.getContext("2d");
  let w = 0;
  let h = 0;
  let t = 0;

  const blobs = [
    { x: 0.15, y: 0.1, r: 0.45, c: [139, 92, 246], s: 0.00035 },
    { x: 0.85, y: 0.15, r: 0.4, c: [236, 72, 153], s: 0.00028 },
    { x: 0.5, y: 0.75, r: 0.5, c: [59, 130, 246], s: 0.00022 },
    { x: 0.2, y: 0.65, r: 0.35, c: [251, 146, 60], s: 0.0003 },
  ];

  function resize() {
    w = canvas.width = window.innerWidth;
    h = canvas.height = window.innerHeight;
  }

  function draw() {
    t += 1;
    ctx.fillStyle = "#030308";
    ctx.fillRect(0, 0, w, h);

    ctx.globalCompositeOperation = "lighter";
    blobs.forEach((b, i) => {
      const px = (b.x + Math.sin(t * b.s + i) * 0.08) * w;
      const py = (b.y + Math.cos(t * b.s * 1.3 + i * 2) * 0.06) * h;
      const rad = b.r * Math.min(w, h);
      const g = ctx.createRadialGradient(px, py, 0, px, py, rad);
      g.addColorStop(0, `rgba(${b.c.join(",")}, 0.22)`);
      g.addColorStop(0.5, `rgba(${b.c.join(",")}, 0.08)`);
      g.addColorStop(1, "rgba(0,0,0,0)");
      ctx.fillStyle = g;
      ctx.fillRect(0, 0, w, h);
    });
    ctx.globalCompositeOperation = "source-over";

    const grid = ctx.createLinearGradient(0, 0, w, h);
    grid.addColorStop(0, "rgba(255,255,255,0.015)");
    grid.addColorStop(1, "rgba(255,255,255,0)");
    ctx.strokeStyle = grid;
    ctx.lineWidth = 1;
    const step = 56;
    for (let x = 0; x < w; x += step) {
      ctx.beginPath();
      ctx.moveTo(x, 0);
      ctx.lineTo(x, h);
      ctx.stroke();
    }
    for (let y = 0; y < h; y += step) {
      ctx.beginPath();
      ctx.moveTo(0, y);
      ctx.lineTo(w, y);
      ctx.stroke();
    }

    requestAnimationFrame(draw);
  }

  window.addEventListener("resize", resize);
  resize();
  draw();
})();
