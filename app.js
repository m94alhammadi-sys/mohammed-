(function () {
  const $ = (id) => document.getElementById(id);
  const money = (n) => `${Number(n).toLocaleString("en-US")} ${STORE.currency}`;
  const igUrl = `https://www.instagram.com/${STORE.instagram}/`;
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

  $("logo").textContent = STORE.name;
  $("storeName").textContent = STORE.name;
  $("tagline").textContent = STORE.tagline;
  $("subtitle").textContent = STORE.subtitle;
  $("note").textContent = STORE.note;
  $("footName").textContent = STORE.name;
  $("year").textContent = new Date().getFullYear();
  $("igLink").href = igUrl;

  let filter = "الكل";
  let query = "";
  const cart = new Map(); // index -> qty

  const categories = ["الكل", ...new Set(PRODUCTS.map((p) => p.category).filter(Boolean))];
  $("filters").innerHTML = categories.map((c) => `<button class="chip${c === filter ? " active" : ""}" data-cat="${esc(c)}">${esc(c)}</button>`).join("");
  $("filters").addEventListener("click", (e) => {
    const b = e.target.closest(".chip");
    if (!b) return;
    filter = b.dataset.cat;
    document.querySelectorAll(".chip").forEach((c) => c.classList.toggle("active", c === b));
    render();
  });
  $("search").addEventListener("input", (e) => { query = e.target.value.trim(); render(); });

  function render() {
    const items = PRODUCTS.map((p, i) => ({ ...p, i })).filter((p) =>
      (filter === "الكل" || p.category === filter) &&
      (!query || (p.name + " " + (p.origin || "") + " " + (p.description || "")).toLowerCase().includes(query.toLowerCase())));
    $("empty").hidden = items.length > 0;
    $("grid").innerHTML = items.map((p) => {
      const soldOut = p.available === false;
      const img = p.image ? `<img src="${esc(p.image)}" alt="${esc(p.name)}" loading="lazy">` : `<span class="ph"><small>${esc(p.origin || "")}</small>${esc(p.name)}</span>`;
      return `<article class="card${soldOut ? " soldout" : ""}">
        <div class="thumb">${img}${p.badge ? `<span class="badge">${esc(p.badge)}</span>` : ""}</div>
        <div class="body">
          ${p.category ? `<span class="cat">${esc(p.category)}</span>` : ""}
          <h3 class="name">${esc(p.name)}</h3>
          ${p.description ? `<p class="desc">${esc(p.description)}</p>` : ""}
          <div class="price-row">
            <span class="price">${money(p.price)}${p.oldPrice ? `<span class="old">${money(p.oldPrice)}</span>` : ""}</span>
            <button class="btn primary add" data-i="${p.i}" ${soldOut ? "disabled" : ""}>أضف</button>
          </div>
        </div>
      </article>`;
    }).join("");
  }

  $("grid").addEventListener("click", (e) => {
    const b = e.target.closest(".add");
    if (!b) return;
    const i = Number(b.dataset.i);
    cart.set(i, (cart.get(i) || 0) + 1);
    renderCart();
    b.textContent = "✓";
    setTimeout(() => (b.textContent = "أضف"), 700);
  });

  function total() {
    let t = 0;
    cart.forEach((q, i) => (t += q * PRODUCTS[i].price));
    return t;
  }

  function renderCart() {
    let count = 0;
    cart.forEach((q) => (count += q));
    $("cartCount").textContent = count;
    $("cartTotal").textContent = money(total());
    $("orderWa").hidden = !STORE.whatsapp;
    $("orderIg").className = "btn full " + (STORE.whatsapp ? "ghost" : "primary");
    $("orderWa").disabled = $("orderIg").disabled = count === 0;
    $("cartItems").innerHTML = count === 0
      ? `<p class="empty">السلة فاضية</p>`
      : [...cart].map(([i, q]) => `<div class="line">
          <div><div class="n">${esc(PRODUCTS[i].name)}</div><div class="p">${money(PRODUCTS[i].price)}</div></div>
          <div class="qty"><button data-i="${i}" data-d="1">+</button><span>${q}</span><button data-i="${i}" data-d="-1">−</button></div>
        </div>`).join("");
  }

  $("cartItems").addEventListener("click", (e) => {
    const b = e.target.closest("button[data-d]");
    if (!b) return;
    const i = Number(b.dataset.i);
    const q = (cart.get(i) || 0) + Number(b.dataset.d);
    q > 0 ? cart.set(i, q) : cart.delete(i);
    renderCart();
  });

  function orderText() {
    const lines = [...cart].map(([i, q]) => `• ${PRODUCTS[i].name} × ${q} = ${money(q * PRODUCTS[i].price)}`);
    return `السلام عليكم، أبغى أطلب:\n${lines.join("\n")}\nالإجمالي: ${money(total())}`;
  }

  const drawer = $("drawer");
  const toggle = (open) => { drawer.classList.toggle("open", open); drawer.setAttribute("aria-hidden", String(!open)); };
  $("cartBtn").onclick = () => toggle(true);
  $("closeCart").onclick = () => toggle(false);
  drawer.addEventListener("click", (e) => { if (e.target === drawer) toggle(false); });

  $("orderWa").onclick = () => window.open(`https://wa.me/${STORE.whatsapp}?text=${encodeURIComponent(orderText())}`, "_blank");
  $("orderIg").onclick = async () => {
    try { await navigator.clipboard.writeText(orderText()); $("igHint").hidden = false; } catch (_) {}
    window.open(`https://ig.me/m/${STORE.instagram}`, "_blank");
  };

  render();
  renderCart();
})();
