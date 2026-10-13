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
    "inbound-section": "inventory",
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

window.addEventListener("hashchange", showDashboardView);
showDashboardView();
