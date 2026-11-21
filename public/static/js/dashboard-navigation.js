"use strict";

const dashboardViews = Array.from(
    document.querySelectorAll("[data-dashboard-view]"),
);
const dashboardLinks = Array.from(
    document.querySelectorAll(".dashboard-menu a[href^='#']"),
);
const legacyViewNames = {
    "employee-section": "employees",
    "customer-section": "customers",
    "product-section": "products",
    "inventory-section": "inbound",
};

function viewNameFromHash() {
    const hash = decodeURIComponent(window.location.hash.slice(1));
    if (!hash) return "overview";
    if (legacyViewNames[hash]) return legacyViewNames[hash];

    const target = document.getElementById(hash);
    return target?.dataset.dashboardView || "overview";
}

function showDashboardView() {
    const selectedView = viewNameFromHash();
    const matchingView = dashboardViews.find(
        (view) => view.dataset.dashboardView === selectedView,
    );
    const activeView = matchingView?.dataset.dashboardView || "overview";

    dashboardViews.forEach((view) => {
        view.hidden = view.dataset.dashboardView !== activeView;
    });
    dashboardLinks.forEach((link) => {
        const target = document.getElementById(
            decodeURIComponent(link.hash.slice(1)),
        );
        const isActive = target?.dataset.dashboardView === activeView;
        if (isActive) {
            link.setAttribute("aria-current", "page");
        } else {
            link.removeAttribute("aria-current");
        }
    });
}

const outboundProduct = document.querySelector("[data-outbound-product]");
const outboundPriceInput = document.querySelector("[data-outbound-price]");
const updateOutboundPrice = () => {
    const price = Number(outboundProduct?.selectedOptions[0]?.dataset.sellingPrice);
    if (outboundPriceInput && Number.isFinite(price)) outboundPriceInput.value = String(Math.round(price));
};
outboundProduct?.addEventListener("change", updateOutboundPrice);
updateOutboundPrice();

window.addEventListener("hashchange", showDashboardView);
showDashboardView();
