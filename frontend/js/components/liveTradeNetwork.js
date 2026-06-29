(function () {
  "use strict";

  const instances = new WeakMap();

  function finite(value, fallback) {
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : (fallback || 0);
  }

  function text(value, fallback) {
    const clean = String(value === undefined || value === null ? "" : value).trim();
    return clean || fallback || "-";
  }

  function normalizeSide(item) {
    const raw = text(item.side || item.direction || item.signal || item.action || item.decision, "neutral").toLowerCase();
    if (/long|buy|al|bull/.test(raw)) return "long";
    if (/short|sell|sat|bear/.test(raw)) return "short";
    return "neutral";
  }

  function normalizeNodes(source, positions, existingNodes) {
    const positionMap = {};
    const existingMap = {};
    (Array.isArray(existingNodes) ? existingNodes : []).forEach(function (node) {
      if (node && node.symbol) existingMap[node.symbol] = node;
    });
    (Array.isArray(positions) ? positions : []).forEach(function (item) {
      const symbol = text(item.symbol || item.coin || item.pair, "");
      if (symbol) positionMap[symbol] = item;
    });

    return (Array.isArray(source) ? source : []).filter(function (item) {
      return item && item.passed === true;
    }).slice(0, 28).map(function (item, index) {
      const symbol = text(item.symbol || item.coin || item.pair || item.asset, "NODE-" + (index + 1));
      const position = positionMap[symbol] || {};
      const seed = symbol.split("").reduce(function (total, char) { return total + char.charCodeAt(0); }, index + 17);
      const existing = existingMap[symbol] || {};
      return {
        symbol: symbol,
        price: finite(item.price || item.lastPrice || item.last_price || item.current_price || position.current_price, 0),
        pnl: finite(item.pnl || item.net_pnl || item.unrealized_pnl || position.pnl || position.unrealized_pnl, 0),
        side: normalizeSide(Object.assign({}, item, position)),
        score: finite(item.score || item.quality_score || item.total_score || item.final_score, 0),
        status: text(item.status || item.result || item.decision, "watch"),
        volume: finite(item.quoteVolume_USDT_24h || item.quote_volume || item.quoteVolume || item.volume, 0),
        xRatio: Number.isFinite(existing.xRatio) ? existing.xRatio : 0.12 + ((seed * 17) % 76) / 100,
        yRatio: Number.isFinite(existing.yRatio) ? existing.yRatio : 0.14 + ((seed * 29) % 70) / 100,
        vx: Number.isFinite(existing.vx) ? existing.vx : (((seed % 7) - 3) || 1) * 0.018,
        vy: Number.isFinite(existing.vy) ? existing.vy : ((((seed * 3) % 7) - 3) || -1) * 0.015
      };
    });
  }

  function placeholderNodes() {
    return normalizeNodes([
      { symbol: "BTCUSDT", side: "neutral", status: "waiting", passed: true },
      { symbol: "ETHUSDT", side: "neutral", status: "waiting", passed: true },
      { symbol: "BNBUSDT", side: "neutral", status: "waiting", passed: true },
      { symbol: "SOLUSDT", side: "neutral", status: "waiting", passed: true }
    ], []);
  }

  function palette(side, automatic) {
    if (automatic) {
      if (side === "short") return { core: "#ff4f8b", glow: "rgba(255,79,139,.24)" };
      if (side === "long") return { core: "#c4ff4d", glow: "rgba(196,255,77,.24)" };
      return { core: "#ffc857", glow: "rgba(255,200,87,.22)" };
    }
    if (side === "short") return { core: "#ff6376", glow: "rgba(255,99,118,.22)" };
    if (side === "long") return { core: "#29e7a6", glow: "rgba(41,231,166,.22)" };
    return { core: "#55d9ff", glow: "rgba(85,217,255,.22)" };
  }

  function createInstance(root, options) {
    const canvas = root.querySelector("canvas");
    const context = canvas && canvas.getContext ? canvas.getContext("2d") : null;
    if (!canvas || !context) return null;

    const instance = {
      root: root,
      canvas: canvas,
      context: context,
      frame: 0,
      width: 0,
      height: 0,
      lastFrameAt: 0,
      lowPower: false,
      options: options || {},
      observer: null
    };

    function resize() {
      const rect = root.getBoundingClientRect();
      const ratio = Math.min(window.devicePixelRatio || 1, 2);
      instance.width = Math.max(320, Math.floor(rect.width));
      instance.height = Math.max(260, Math.floor(rect.height));
      canvas.width = Math.floor(instance.width * ratio);
      canvas.height = Math.floor(instance.height * ratio);
      canvas.style.width = instance.width + "px";
      canvas.style.height = instance.height + "px";
      context.setTransform(ratio, 0, 0, ratio, 0, 0);
    }

    function drawGrid() {
      const ctx = context;
      ctx.strokeStyle = instance.options.automatic ? "rgba(255,200,87,.08)" : "rgba(85,217,255,.07)";
      ctx.lineWidth = 1;
      for (let x = 0; x <= instance.width; x += 42) {
        ctx.beginPath();
        ctx.moveTo(x, 0);
        ctx.lineTo(x, instance.height);
        ctx.stroke();
      }
      for (let y = 0; y <= instance.height; y += 42) {
        ctx.beginPath();
        ctx.moveTo(0, y);
        ctx.lineTo(instance.width, y);
        ctx.stroke();
      }
    }

    function drawNode(node, index) {
      const ctx = context;
      const x = node.xRatio * instance.width;
      const y = node.yRatio * instance.height;
      const color = palette(node.side, instance.options.automatic);
      const radius = 5 + Math.min(Math.abs(node.score) / 18, 5);

      ctx.beginPath();
      ctx.fillStyle = color.glow;
      ctx.arc(x, y, radius + 9, 0, Math.PI * 2);
      ctx.fill();
      ctx.beginPath();
      ctx.fillStyle = color.core;
      ctx.arc(x, y, radius, 0, Math.PI * 2);
      ctx.fill();

      ctx.font = "700 11px system-ui, sans-serif";
      ctx.fillStyle = "#eefbff";
      ctx.fillText(node.symbol, x + 11, y - 5);
      ctx.font = "10px system-ui, sans-serif";
      ctx.fillStyle = "rgba(205,238,248,.74)";
      const detail = node.pnl ? ((node.pnl > 0 ? "+" : "") + node.pnl.toFixed(2) + " PnL") : (node.price ? node.price.toFixed(node.price < 1 ? 5 : 2) : node.status);
      ctx.fillText(detail, x + 11, y + 9);

      if (index > 0) {
        const previous = instance.nodes[index - 1];
        ctx.beginPath();
        ctx.strokeStyle = instance.options.automatic ? "rgba(255,200,87,.13)" : "rgba(85,217,255,.13)";
        ctx.moveTo(previous.xRatio * instance.width, previous.yRatio * instance.height);
        ctx.lineTo(x, y);
        ctx.stroke();
      }
    }

    function animate(timestamp) {
      if (!root.isConnected) {
        if (instance.observer) instance.observer.disconnect();
        return;
      }
      const elapsed = timestamp - (instance.lastFrameAt || timestamp);
      instance.lastFrameAt = timestamp;
      instance.lowPower = elapsed > 42 || document.hidden || Boolean(window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches);
      context.clearRect(0, 0, instance.width, instance.height);
      drawGrid();

      const speed = instance.options.botRunning ? (instance.lowPower ? 0.18 : 0.55) : 0.025;
      instance.nodes.forEach(function (node, index) {
        node.xRatio += node.vx * speed;
        node.yRatio += node.vy * speed;
        if (node.xRatio < 0.06 || node.xRatio > 0.92) node.vx *= -1;
        if (node.yRatio < 0.08 || node.yRatio > 0.9) node.vy *= -1;
        drawNode(node, index);
      });

      instance.frame = window.requestAnimationFrame(animate);
    }

    instance.nodes = normalizeNodes(instance.options.nodes, instance.options.positions);
    if (!instance.nodes.length && instance.options.allowPlaceholder !== false) instance.nodes = placeholderNodes();
    resize();
    if (typeof ResizeObserver !== "undefined") {
      instance.observer = new ResizeObserver(resize);
      instance.observer.observe(root);
    } else {
      window.addEventListener("resize", resize);
    }
    instance.frame = window.requestAnimationFrame(animate);
    return instance;
  }

  window.HMTSTC_LIVE_TRADE_NETWORK = {
    unmount: function (rootOrSelector) {
      const root = typeof rootOrSelector === "string" ? document.querySelector(rootOrSelector) : rootOrSelector;
      if (!root) return false;
      const previous = instances.get(root);
      if (!previous) return false;
      window.cancelAnimationFrame(previous.frame);
      if (previous.observer) previous.observer.disconnect();
      instances.delete(root);
      return true;
    },

    mount: function (rootOrSelector, options) {
      const root = typeof rootOrSelector === "string" ? document.querySelector(rootOrSelector) : rootOrSelector;
      if (!root) return false;
      const previous = instances.get(root);
      if (previous) {
        previous.options = options || {};
        previous.nodes = normalizeNodes(previous.options.nodes, previous.options.positions, previous.nodes);
        if (!previous.nodes.length && previous.options.allowPlaceholder !== false) previous.nodes = placeholderNodes();
        return true;
      }
      const instance = createInstance(root, options || {});
      if (instance) instances.set(root, instance);
      return Boolean(instance);
    }
  };
}());
