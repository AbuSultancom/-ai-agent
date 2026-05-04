const I18N = {
  en: {
    // nav
    home: "Home", products: "Products", cart: "Cart", checkout: "Checkout",
    search_placeholder: "Search products...", lang_toggle: "العربية",
    // hero
    hero_title: "Shop Everything, Everywhere",
    hero_sub: "Products from all your favourite stores in one place.",
    shop_now: "Shop Now",
    // sections
    featured: "Featured Products", all_products: "All Products",
    categories: "Categories", new_arrivals: "New Arrivals",
    // product card
    add_to_cart: "Add to Cart", view_details: "View Details",
    in_stock: "In Stock", out_of_stock: "Out of Stock",
    sar: "SAR", items: "items",
    // filters
    filter: "Filter", sort_by: "Sort by", price_range: "Price Range",
    min: "Min", max: "Max", apply: "Apply", reset: "Reset",
    sort_newest: "Newest", sort_price_asc: "Price: Low to High",
    sort_price_desc: "Price: High to Low", sort_name: "Name",
    source: "Source", all_sources: "All Sources",
    // cart
    your_cart: "Your Cart", empty_cart: "Your cart is empty",
    quantity: "Quantity", remove: "Remove", subtotal: "Subtotal",
    tax: "VAT (15%)", shipping: "Shipping", total: "Total",
    proceed_checkout: "Proceed to Checkout", continue_shopping: "Continue Shopping",
    free_shipping: "Free", free_shipping_note: "Free shipping on orders over 200 SAR",
    // checkout
    checkout_title: "Checkout", customer_info: "Customer Information",
    full_name: "Full Name", email: "Email Address", phone: "Phone Number",
    shipping_address: "Shipping Address", address: "Address",
    city: "City", country: "Country", order_notes: "Order Notes (optional)",
    place_order: "Place Order", order_summary: "Order Summary",
    // success
    order_success: "Order Placed Successfully!",
    order_success_msg: "Thank you! Your order has been received.",
    order_number: "Order Number", track_order: "Track Order",
    back_home: "Back to Home",
    // product detail
    description: "Description", related: "Related Products",
    stock_left: "left in stock", share: "Share",
    // messages
    added_to_cart: "Added to cart!", loading: "Loading...",
    error_loading: "Error loading products. Please try again.",
    no_products: "No products found.", processing: "Processing...",
    // stores
    sources_title: "Connected Stores", powered_by: "Powered by AI",
    // footer
    footer_tagline: "Your unified shopping destination.",
    footer_links: "Quick Links", footer_contact: "Contact",
    rights: "All rights reserved.",
  },
  ar: {
    // nav
    home: "الرئيسية", products: "المنتجات", cart: "السلة", checkout: "الدفع",
    search_placeholder: "ابحث عن منتجات...", lang_toggle: "English",
    // hero
    hero_title: "تسوّق كل شيء، في كل مكان",
    hero_sub: "منتجات من جميع متاجرك المفضلة في مكان واحد.",
    shop_now: "تسوّق الآن",
    // sections
    featured: "منتجات مميزة", all_products: "جميع المنتجات",
    categories: "التصنيفات", new_arrivals: "وصل حديثاً",
    // product card
    add_to_cart: "أضف إلى السلة", view_details: "عرض التفاصيل",
    in_stock: "متوفر", out_of_stock: "غير متوفر",
    sar: "ر.س", items: "منتجات",
    // filters
    filter: "تصفية", sort_by: "ترتيب حسب", price_range: "نطاق السعر",
    min: "أدنى", max: "أعلى", apply: "تطبيق", reset: "إعادة تعيين",
    sort_newest: "الأحدث", sort_price_asc: "السعر: من الأقل للأعلى",
    sort_price_desc: "السعر: من الأعلى للأقل", sort_name: "الاسم",
    source: "المصدر", all_sources: "جميع المصادر",
    // cart
    your_cart: "سلة التسوق", empty_cart: "سلتك فارغة",
    quantity: "الكمية", remove: "حذف", subtotal: "المجموع الجزئي",
    tax: "ضريبة القيمة المضافة (15%)", shipping: "الشحن", total: "الإجمالي",
    proceed_checkout: "المتابعة للدفع", continue_shopping: "مواصلة التسوق",
    free_shipping: "مجاني", free_shipping_note: "شحن مجاني للطلبات فوق 200 ر.س",
    // checkout
    checkout_title: "إتمام الشراء", customer_info: "بيانات العميل",
    full_name: "الاسم الكامل", email: "البريد الإلكتروني", phone: "رقم الهاتف",
    shipping_address: "عنوان الشحن", address: "العنوان",
    city: "المدينة", country: "الدولة", order_notes: "ملاحظات الطلب (اختياري)",
    place_order: "تأكيد الطلب", order_summary: "ملخص الطلب",
    // success
    order_success: "تم الطلب بنجاح!",
    order_success_msg: "شكراً لك! تم استلام طلبك.",
    order_number: "رقم الطلب", track_order: "تتبع الطلب",
    back_home: "العودة للرئيسية",
    // product detail
    description: "الوصف", related: "منتجات مشابهة",
    stock_left: "متبقي في المخزون", share: "مشاركة",
    // messages
    added_to_cart: "تمت الإضافة إلى السلة!", loading: "جاري التحميل...",
    error_loading: "خطأ في تحميل المنتجات. يرجى المحاولة مرة أخرى.",
    no_products: "لا توجد منتجات.", processing: "جاري المعالجة...",
    // stores
    sources_title: "المتاجر المتصلة", powered_by: "مدعوم بالذكاء الاصطناعي",
    // footer
    footer_tagline: "وجهتك الموحّدة للتسوق.",
    footer_links: "روابط سريعة", footer_contact: "تواصل معنا",
    rights: "جميع الحقوق محفوظة.",
  }
};

class Store {
  constructor() {
    this.lang = localStorage.getItem("lang") || "en";
    this.cart = JSON.parse(localStorage.getItem("cart") || "[]");
    this.applyLang();
  }

  t(key) { return (I18N[this.lang] || I18N.en)[key] || key; }

  setLang(lang) {
    this.lang = lang;
    localStorage.setItem("lang", lang);
    this.applyLang();
  }

  toggleLang() {
    this.setLang(this.lang === "en" ? "ar" : "en");
    location.reload();
  }

  applyLang() {
    const isAr = this.lang === "ar";
    document.documentElement.setAttribute("dir", isAr ? "rtl" : "ltr");
    document.documentElement.setAttribute("lang", this.lang);
    document.querySelectorAll("[data-i18n]").forEach(el => {
      const key = el.getAttribute("data-i18n");
      if (el.tagName === "INPUT" || el.tagName === "TEXTAREA") {
        el.placeholder = this.t(key);
      } else {
        el.textContent = this.t(key);
      }
    });
  }

  // ── Cart ──────────────────────────────────────────────────────────────────
  addToCart(product) {
    const existing = this.cart.find(i => i.id === product.id && i.source === product.source);
    if (existing) {
      existing.quantity = Math.min(existing.quantity + 1, product.stock || 99);
    } else {
      this.cart.push({ ...product, quantity: 1 });
    }
    this.saveCart();
    this.updateCartBadge();
    this.showToast(this.t("added_to_cart"), "success");
  }

  removeFromCart(index) {
    this.cart.splice(index, 1);
    this.saveCart();
    this.updateCartBadge();
  }

  updateQty(index, qty) {
    if (qty < 1) { this.removeFromCart(index); return; }
    this.cart[index].quantity = qty;
    this.saveCart();
  }

  clearCart() { this.cart = []; this.saveCart(); this.updateCartBadge(); }

  saveCart() { localStorage.setItem("cart", JSON.stringify(this.cart)); }

  get cartTotal() {
    return this.cart.reduce((s, i) => s + i.price * i.quantity, 0);
  }

  get cartCount() {
    return this.cart.reduce((s, i) => s + i.quantity, 0);
  }

  updateCartBadge() {
    document.querySelectorAll(".cart-badge").forEach(el => {
      const count = this.cartCount;
      el.textContent = count;
      el.style.display = count > 0 ? "flex" : "none";
    });
  }

  // ── API helpers ───────────────────────────────────────────────────────────
  async fetchProducts(params = {}) {
    const qs = new URLSearchParams(params).toString();
    const res = await fetch(`/api/store/products${qs ? "?" + qs : ""}`);
    return res.json();
  }

  async fetchProduct(id) {
    const res = await fetch(`/api/store/products/${id}`);
    return res.json();
  }

  async placeOrder(payload) {
    const res = await fetch("/api/store/checkout", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    return res.json();
  }

  // ── Toast ──────────────────────────────────────────────────────────────────
  showToast(msg, type = "info") {
    const el = document.createElement("div");
    const colors = { success: "bg-green-500", error: "bg-red-500", info: "bg-blue-500" };
    el.className = `fixed bottom-6 ${this.lang === "ar" ? "left-6" : "right-6"} z-50 px-5 py-3 rounded-lg text-white shadow-lg text-sm font-medium transition-all ${colors[type] || colors.info}`;
    el.textContent = msg;
    document.body.appendChild(el);
    setTimeout(() => { el.style.opacity = "0"; setTimeout(() => el.remove(), 300); }, 2500);
  }

  // ── Price format ──────────────────────────────────────────────────────────
  formatPrice(price) {
    const num = parseFloat(price).toFixed(2);
    return this.lang === "ar" ? `${num} ${this.t("sar")}` : `${this.t("sar")} ${num}`;
  }

  // ── Source badge ──────────────────────────────────────────────────────────
  sourceBadge(source) {
    const colors = {
      shopify: "bg-green-100 text-green-700",
      salla: "bg-orange-100 text-orange-700",
      zid: "bg-purple-100 text-purple-700",
      local: "bg-blue-100 text-blue-700",
    };
    const labels = { shopify: "Shopify", salla: "Salla سلة", zid: "Zid زد", local: "Local" };
    const cls = colors[source] || "bg-gray-100 text-gray-700";
    return `<span class="text-xs font-semibold px-2 py-0.5 rounded-full ${cls}">${labels[source] || source}</span>`;
  }

  // ── Product card HTML ─────────────────────────────────────────────────────
  productCard(p) {
    const inStock = p.stock > 0;
    return `
    <div class="bg-white rounded-2xl shadow-sm hover:shadow-md transition-all overflow-hidden group border border-gray-100">
      <div class="relative overflow-hidden aspect-square bg-gray-50">
        ${p.image_url
          ? `<img src="${p.image_url}" alt="${p.name}" class="w-full h-full object-cover group-hover:scale-105 transition-transform duration-300" loading="lazy">`
          : `<div class="w-full h-full flex items-center justify-center text-gray-300"><svg class="w-16 h-16" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M4 16l4.586-4.586a2 2 0 012.828 0L16 16m-2-2l1.586-1.586a2 2 0 012.828 0L20 14m-6-6h.01M6 20h12a2 2 0 002-2V6a2 2 0 00-2-2H6a2 2 0 00-2 2v12a2 2 0 002 2z"/></svg></div>`
        }
        <div class="absolute top-2 ${this.lang === "ar" ? "right-2" : "left-2"}">${this.sourceBadge(p.source)}</div>
        ${!inStock ? `<div class="absolute inset-0 bg-white/60 flex items-center justify-center"><span class="text-red-600 font-bold text-sm">${this.t("out_of_stock")}</span></div>` : ""}
      </div>
      <div class="p-4">
        <p class="text-xs text-gray-400 mb-1">${p.category || ""}</p>
        <h3 class="font-semibold text-gray-800 text-sm leading-tight mb-2 line-clamp-2">${p.name}</h3>
        <div class="flex items-center justify-between mt-3">
          <span class="text-lg font-bold text-indigo-600">${this.formatPrice(p.price)}</span>
          ${inStock
            ? `<button onclick='window.store.addToCart(${JSON.stringify(p)})'
                class="bg-indigo-600 hover:bg-indigo-700 text-white text-xs font-semibold px-3 py-1.5 rounded-lg transition-colors">
                ${this.t("add_to_cart")}
               </button>`
            : `<span class="text-xs text-red-500">${this.t("out_of_stock")}</span>`
          }
        </div>
        <a href="/store/products/${p.source_id || p.id}" class="block mt-2 text-center text-xs text-indigo-500 hover:text-indigo-700">${this.t("view_details")}</a>
      </div>
    </div>`;
  }
}

window.store = new Store();
document.addEventListener("DOMContentLoaded", () => {
  window.store.updateCartBadge();
  window.store.applyLang();
});
