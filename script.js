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

// ===== Contact Forms =====
function handleFormSubmit(formId, successId) {
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
                form.reset();
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

handleFormSubmit('contactForm', 'contactSuccess');
handleFormSubmit('evalForm', 'evalSuccess');

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
