// ===== Navbar scroll effect =====
const navbar = document.getElementById('navbar');
window.addEventListener('scroll', () => {
    navbar.classList.toggle('scrolled', window.scrollY > 60);
});

// ===== Mobile nav toggle =====
const navToggle = document.getElementById('navToggle');
const navLinks = document.getElementById('navLinks');

navToggle.addEventListener('click', () => {
    navLinks.classList.toggle('active');
});

// Close mobile nav on link click
navLinks.querySelectorAll('a').forEach(link => {
    link.addEventListener('click', () => {
        navLinks.classList.remove('active');
    });
});

// ===== Lightbox =====
const lightbox = document.getElementById('lightbox');
const lightboxImg = document.getElementById('lightboxImg');
const lightboxCounter = document.getElementById('lightboxCounter');
const galleryItems = document.querySelectorAll('.gallery-item');

// Collect all gallery image srcs
const images = [];
galleryItems.forEach(item => {
    const img = item.querySelector('img');
    if (img) images.push(img.src);
});

let currentIndex = 0;

function openLightbox(index) {
    currentIndex = index;
    lightboxImg.src = images[currentIndex];
    lightboxCounter.textContent = (currentIndex + 1) + ' / ' + images.length;
    lightbox.classList.add('active');
    document.body.style.overflow = 'hidden';
}

function closeLightbox() {
    lightbox.classList.remove('active');
    document.body.style.overflow = '';
}

function nextImage() {
    currentIndex = (currentIndex + 1) % images.length;
    lightboxImg.src = images[currentIndex];
    lightboxCounter.textContent = (currentIndex + 1) + ' / ' + images.length;
}

function prevImage() {
    currentIndex = (currentIndex - 1 + images.length) % images.length;
    lightboxImg.src = images[currentIndex];
    lightboxCounter.textContent = (currentIndex + 1) + ' / ' + images.length;
}

galleryItems.forEach(item => {
    item.addEventListener('click', () => {
        const index = parseInt(item.dataset.index);
        openLightbox(index);
    });
});

document.querySelector('.lightbox-close').addEventListener('click', closeLightbox);
document.querySelector('.lightbox-prev').addEventListener('click', prevImage);
document.querySelector('.lightbox-next').addEventListener('click', nextImage);

lightbox.addEventListener('click', (e) => {
    if (e.target === lightbox) closeLightbox();
});

document.addEventListener('keydown', (e) => {
    if (!lightbox.classList.contains('active')) return;
    if (e.key === 'Escape') closeLightbox();
    if (e.key === 'ArrowRight') nextImage();
    if (e.key === 'ArrowLeft') prevImage();
});

// ===== Lead attribution =====
// Stamps every form submission with where the visitor came from, so an emailed
// lead can be traced back to the ad that produced it. Values are read from the
// landing URL (UTM tags / fbclid) and kept for the session in case the visitor
// navigates around before converting.
const LEAD_ATTRIBUTION_KEY = 'wateroak_lead_attribution';

function readAttributionFromUrl() {
    const params = new URLSearchParams(window.location.search);
    const source = params.get('utm_source');
    const medium = params.get('utm_medium');
    const campaign = params.get('utm_campaign');
    const content = params.get('utm_content');
    const hasFbClick = params.has('fbclid');

    if (!source && !campaign && !hasFbClick) return null;

    let label;
    if (source) {
        label = medium ? source + ' / ' + medium : source;
    } else {
        label = 'facebook / paid';
    }

    return {
        source: label,
        campaign: [campaign, content].filter(Boolean).join(' – ')
    };
}

function getAttribution() {
    const fromUrl = readAttributionFromUrl();
    if (fromUrl) {
        try {
            sessionStorage.setItem(LEAD_ATTRIBUTION_KEY, JSON.stringify(fromUrl));
        } catch (e) { /* private browsing — fall through, the URL value still applies */ }
        return fromUrl;
    }
    try {
        const stored = sessionStorage.getItem(LEAD_ATTRIBUTION_KEY);
        if (stored) return JSON.parse(stored);
    } catch (e) { /* ignore */ }
    return null;
}

function applyAttribution() {
    const attribution = getAttribution();
    if (!attribution) return;
    document.querySelectorAll('.js-lead-source').forEach(input => {
        input.value = attribution.source;
    });
    document.querySelectorAll('.js-lead-campaign').forEach(input => {
        input.value = attribution.campaign;
    });
}

applyAttribution();

// ===== Meta Pixel events =====
// No-ops safely until a real Pixel ID is set in index.html.
function trackPixel(event, params) {
    if (typeof fbq !== 'function') return;
    fbq('track', event, params || {});
}

// Count a tap on the phone number as an intent signal.
document.querySelectorAll('a[href^="tel:"]').forEach(link => {
    link.addEventListener('click', () => {
        trackPixel('Contact', { content_name: '2147 Wateroak Dr', method: 'phone' });
    });
});

// ===== Contact Forms =====
function handleFormSubmit(formId, successId, leadType) {
    const form = document.getElementById(formId);
    const success = document.getElementById(successId);
    form.addEventListener('submit', (e) => {
        e.preventDefault();
        const submitBtn = form.querySelector('button[type="submit"]');
        const originalText = submitBtn.textContent;
        submitBtn.textContent = 'Sending...';
        submitBtn.disabled = true;
        const formData = new FormData(form);
        fetch(form.action, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', 'Accept': 'application/json' },
            body: JSON.stringify(Object.fromEntries(formData))
        }).then((response) => {
            if (!response.ok) throw new Error('Form submission failed');
            return response.json();
        }).then((data) => {
            if (data.success) {
                trackPixel('Lead', {
                    content_name: '2147 Wateroak Dr',
                    content_category: leadType,
                    value: 839000,
                    currency: 'CAD'
                });
                form.reset();
                applyAttribution(); // reset() restores hidden defaults — re-stamp them
                success.textContent = 'Thank you! We will be in touch shortly.';
                success.classList.remove('error');
                success.classList.add('show');
                setTimeout(() => success.classList.remove('show'), 5000);
            } else {
                throw new Error('Submission error');
            }
        }).catch(() => {
            success.textContent = 'Something went wrong. Please call 647.868.6248 or email Puneetpruthi11@gmail.com directly.';
            success.classList.add('show', 'error');
            setTimeout(() => success.classList.remove('show', 'error'), 8000);
        }).finally(() => {
            submitBtn.textContent = originalText;
            submitBtn.disabled = false;
        });
    });
}

handleFormSubmit('contactForm', 'contactSuccess', 'Showing Request');
handleFormSubmit('evalForm', 'evalSuccess', 'Home Evaluation');

// ===== Scroll animations =====
const observerOptions = { threshold: 0.1, rootMargin: '0px 0px -50px 0px' };

const observer = new IntersectionObserver((entries) => {
    entries.forEach(entry => {
        if (entry.isIntersecting) {
            entry.target.classList.add('visible');
        }
    });
}, observerOptions);

document.querySelectorAll('.feature-card, .location-card, .detail-item, .gallery-item').forEach(el => {
    el.classList.add('animate-in');
    observer.observe(el);
});

// CSS for animations (injected)
const style = document.createElement('style');
style.textContent = `
    .animate-in {
        opacity: 0;
        transform: translateY(20px);
        transition: opacity 0.6s ease, transform 0.6s ease;
    }
    .animate-in.visible {
        opacity: 1;
        transform: translateY(0);
    }
`;
document.head.appendChild(style);
