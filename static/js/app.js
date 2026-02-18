// ============================================
// APPLICATION PRINCIPALE
// ============================================

let currentLang = 'fr';
let currentUser = null;
let timerInterval = null;

function initApp(lang, user) {
    currentLang = lang;
    currentUser = user;
    
    // Charger la langue
    changeLang(lang);
    
    // Démarrer le timer d'abonnement
    startSubscriptionTimer();
    
    // Charger les données
    fetchData();
    setInterval(fetchData, 3000);
}

function changeLang(lang) {
    currentLang = lang;
    const t = TRANSLATIONS[lang];
    
    // Mettre à jour tous les éléments avec data-translate
    document.querySelectorAll('[data-translate]').forEach(el => {
        const key = el.dataset.translate;
        if (t[key]) {
            el.textContent = t[key];
        }
    });
    
    // Mettre à jour le drapeau
    const flagEl = document.getElementById('userFlag');
    if (flagEl && t.flag) {
        flagEl.textContent = t.flag;
    }
    
    localStorage.setItem('preferred_lang', lang);
    
    // Forcer la mise à jour des prédictions pour appliquer la langue immédiatement
    fetchData();
}

function getSuitDisplay(suit) {
    const t = TRANSLATIONS[currentLang] || TRANSLATIONS.fr;
    const displays = {
        '♠': `♠️ ${t.suit_spade || 'Pique'}`,
        '♥': `❤️ ${t.suit_heart || 'Cœur'}`,
        '♦': `♦️ ${t.suit_diamond || 'Carreau'}`,
        '♣': `♣️ ${t.suit_club || 'Trèfle'}`
    };
    return displays[suit] || suit;
}

function getSuitClass(suit) {
    return `suit-${suit === '♥' ? 'heart' : suit === '♦' ? 'diamond' : suit === '♣' ? 'club' : 'spade'}`;
}

function renderHistory(predictions) {
    const grid = document.getElementById('historyGrid');
    grid.innerHTML = '<p style="grid-column: 1/span 4; text-align: center; opacity: 0.5;">Historique désactivé</p>';
}

function updateActivePrediction(predictions) {
    const t = TRANSLATIONS[currentLang] || TRANSLATIONS.fr;
    
    // Trouver la prédiction en attente (statut ⏳)
    const active = predictions.find(p => p.status === '⏳');
    
    const activePredictionDiv = document.getElementById('activePrediction');
    const largePredictionBox = document.getElementById('largePredictionBox');
    const largePredNumber = document.getElementById('largePredNumber');
    const largePredSuit = document.getElementById('largePredSuit');
    const largePredStatus = document.getElementById('largePredStatus');
    
    const numberEl = document.getElementById('predNumber');
    const suitEl = document.getElementById('predSuit');
    const statusEl = document.getElementById('predStatus');
    const timeEl = document.getElementById('predTime');
    
    if (!active) {
        if (activePredictionDiv) activePredictionDiv.style.display = 'none';
        if (largePredictionBox) largePredictionBox.style.display = 'none';
        return;
    }
    
    // Bloc standard (caché comme demandé pour ne voir que le live large)
    if (activePredictionDiv) activePredictionDiv.style.display = 'none';
    
    // Nouveau Bloc Large - Affichage en temps réel
    if (largePredictionBox) {
        largePredictionBox.style.display = 'block';
        largePredNumber.textContent = `🎰 ${t.prediction || 'PRÉDICTION'} #${active.game_number}`;
        largePredSuit.textContent = `🎯 ${t.suit_label || 'Couleur'}: ${getSuitDisplay(active.suit)}`;
        largePredStatus.textContent = `📊 ${t.status_label || 'Statut'}: ${t.waiting_result || 'EN ATTENTE DU RÉSULTAT...'}`;
    }
}

function startSubscriptionTimer() {
    if (!currentUser || !currentUser.subscription_end) {
        showExpiredModal();
        return;
    }
    
    const updateTimer = () => {
        const end = new Date(currentUser.subscription_end);
        const now = new Date();
        const diff = end - now;
        
        const timerDisplay = document.getElementById('timerDisplay');
        const timerValue = document.getElementById('timerValue');
        
        if (diff <= 0) {
            timerValue.textContent = '00:00:00';
            timerDisplay.classList.add('expired');
            showExpiredModal();
            clearInterval(timerInterval);
            return;
        }
        
        const days = Math.floor(diff / 86400000);
        const hours = Math.floor((diff % 86400000) / 3600000);
        const minutes = Math.floor((diff % 3600000) / 60000);
        const seconds = Math.floor((diff % 60000) / 1000);
        
        if (days > 0) {
            timerValue.textContent = `${days}j ${hours.toString().padStart(2, '0')}h`;
        } else {
            timerValue.textContent = `${hours.toString().padStart(2, '0')}:${minutes.toString().padStart(2, '0')}:${seconds.toString().padStart(2, '0')}`;
        }
    };
    
    updateTimer();
    timerInterval = setInterval(updateTimer, 1000);
}

function showExpiredModal() {
    const modal = document.getElementById('expiredModal');
    const userName = document.getElementById('expiredUserName');
    
    if (currentUser) {
        userName.textContent = currentUser.first_name;
    }
    
    modal.classList.remove('hidden');
}

async function fetchData() {
    try {
        const res = await fetch('/api/predictions');
        if (!res.ok) {
            if (res.status === 401) {
                window.location = '/login';
            }
            return;
        }
        
        const data = await res.json();
        
        // Mettre à jour les stats
        document.getElementById('winRateValue').textContent = data.win_rate + '%';
        document.getElementById('wonValue').textContent = data.won_predictions;
        document.getElementById('lostValue').textContent = data.lost_predictions;
        
        // Mise à jour des nouveaux compteurs (Préd. restantes et Pause)
        if (data.pause_info) {
            const predRemEl = document.getElementById('topWonCount');
            const pauseValEl = document.getElementById('topLostCount');
            
            if (predRemEl) predRemEl.textContent = data.pause_info.remaining_before_pause;
            
            if (data.pause_info.is_paused) {
                if (pauseValEl) {
                    pauseValEl.textContent = data.pause_info.remaining_pause_time;
                    pauseValEl.style.color = '#ff4b2b';
                }
            } else {
                if (pauseValEl) {
                    pauseValEl.textContent = "0";
                    pauseValEl.style.color = '';
                }
            }
        }
        
        document.getElementById('progressHeader').textContent = 
            `${data.won_predictions + data.lost_predictions} / ${data.total_predictions}`;
        
        if (data.last_source_game) {
            document.getElementById('sourceGameNumber').textContent = '#' + data.last_source_game;
        }

        // Update Pause Info
        const pauseInfoBar = document.getElementById('pauseInfoBar');
        if (pauseInfoBar) {
            if (data.pause_info) {
                pauseInfoBar.style.display = 'flex';
                document.getElementById('predRemaining').textContent = data.pause_info.remaining_before_pause;
                const pauseTimerBox = document.getElementById('pauseTimerBox');
                const pauseTimerValue = document.getElementById('pauseTimerValue');
                
                if (data.pause_info.is_paused) {
                    pauseTimerBox.style.display = 'block';
                    pauseTimerValue.textContent = data.pause_info.remaining_pause_time;
                } else {
                    pauseTimerBox.style.display = 'none';
                }
            } else {
                pauseInfoBar.style.display = 'none';
            }
        }
        
        // Mettre à jour la prédiction active
        updateActivePrediction(data.predictions);
        
        // Rendre l'historique
        renderHistory(data.predictions);
        
    } catch (e) {
        console.error('Fetch error:', e);
    }
}

async function logout() {
    await fetch('/api/logout', {method: 'POST'});
    window.location = '/login';
}

// Gestionnaire de sélection de langue
document.getElementById('langSelect')?.addEventListener('change', (e) => {
    changeLang(e.target.value);
});
