document.addEventListener("DOMContentLoaded", () => {
    const mainImage = document.querySelector("[data-product-main-image]");
    const thumbnails = document.querySelectorAll("[data-product-thumbnail]");

    if (!mainImage || thumbnails.length < 2) {
        return;
    }

    thumbnails.forEach((thumbnail) => {
        thumbnail.addEventListener("click", () => {
            mainImage.src = thumbnail.dataset.imageUrl;
            thumbnails.forEach((item) => {
                const isActive = item === thumbnail;
                item.classList.toggle("is-active", isActive);
                item.setAttribute("aria-pressed", String(isActive));
            });
        });
    });
});
