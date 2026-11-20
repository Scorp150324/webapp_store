document.addEventListener("DOMContentLoaded", () => {
    const carousel = document.querySelector("[data-product-carousel]");
    if (!carousel) {
        return;
    }

    const slides = Array.from(carousel.querySelectorAll("[data-carousel-slide]"));
    if (slides.length < 2) {
        return;
    }

    const dots = Array.from(carousel.querySelectorAll("[data-carousel-dot]"));
    const previousButton = carousel.querySelector("[data-carousel-prev]");
    const nextButton = carousel.querySelector("[data-carousel-next]");
    const toggleButton = carousel.querySelector("[data-carousel-toggle]");
    const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    if (reducedMotion) {
        toggleButton.hidden = true;
    }

    let activeIndex = 0;
    let timer = null;
    let manuallyPaused = false;
    let pointerInside = false;
    let focusInside = false;

    const stopAutoplay = () => {
        if (timer !== null) {
            window.clearInterval(timer);
            timer = null;
        }
    };

    const startAutoplay = () => {
        stopAutoplay();
        if (
            manuallyPaused ||
            pointerInside ||
            focusInside ||
            document.hidden ||
            reducedMotion
        ) {
            return;
        }

        timer = window.setInterval(() => {
            showSlide(activeIndex + 1);
        }, 5500);
    };

    const showSlide = (index) => {
        activeIndex = (index + slides.length) % slides.length;
        slides.forEach((slide, slideIndex) => {
            const isActive = slideIndex === activeIndex;
            slide.classList.toggle("is-active", isActive);
            slide.setAttribute("aria-hidden", String(!isActive));
        });
        dots.forEach((dot, dotIndex) => {
            const isActive = dotIndex === activeIndex;
            dot.classList.toggle("is-active", isActive);
            dot.setAttribute("aria-current", String(isActive));
        });
    };

    previousButton.addEventListener("click", () => {
        showSlide(activeIndex - 1);
        startAutoplay();
    });
    nextButton.addEventListener("click", () => {
        showSlide(activeIndex + 1);
        startAutoplay();
    });
    dots.forEach((dot) => {
        dot.addEventListener("click", () => {
            showSlide(Number(dot.dataset.carouselDot));
            startAutoplay();
        });
    });
    toggleButton.addEventListener("click", () => {
        manuallyPaused = !manuallyPaused;
        toggleButton.textContent = manuallyPaused ? "Tiếp tục" : "Tạm dừng";
        toggleButton.setAttribute("aria-pressed", String(manuallyPaused));
        startAutoplay();
    });

    carousel.addEventListener("pointerenter", () => {
        pointerInside = true;
        stopAutoplay();
    });
    carousel.addEventListener("pointerleave", () => {
        pointerInside = false;
        startAutoplay();
    });
    carousel.addEventListener("focusin", () => {
        focusInside = true;
        stopAutoplay();
    });
    carousel.addEventListener("focusout", (event) => {
        if (!carousel.contains(event.relatedTarget)) {
            focusInside = false;
            startAutoplay();
        }
    });
    document.addEventListener("visibilitychange", startAutoplay);

    startAutoplay();
});
