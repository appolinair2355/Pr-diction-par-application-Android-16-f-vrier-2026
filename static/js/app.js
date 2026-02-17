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
}

function getSuitDisplay(suit) {
    const displays = {
        '♠': '♠️ Pique',
        '♥': '❤️ Cœur',
        '♦': '♦️ Carreau',
        '♣': '♣️ Trèfle'
    };
    return displays[suit] || suit;
}

function getSuitClass(suit) {
    return `suit-${suit === '♥' ? 'heart' : suit === '♦' ? 'diamond' : suit === '♣' ? 'club' : 'spade'}`;
}

function renderHistory(predictions) {
    const grid = document.getElementById('historyGrid');
    const recent = predictions.slice(-12).reverse();
    
    if (recent.length === 0) {
        grid.innerHTML = '<p style="grid-column: 4; text-align: center; opacity: 0.5;">Aucune prédiction</p>';
        return;
    }
    
    grid.innerHTML = recent.map(pred => {
        let statusClass = 'pending';
        if (pred.status.includes('✅')) statusClass = 'won';
        else if (pred.status.includes('❌')) statusClass = 'lost';
        
        return `
            <div class="history-item ${statusClass}">
                <div class="num">#${pred.game_number}</div>
                <div class="suit ${getSuitClass(pred.suit)}">${pred.suit}</div>
                <div class="time">${pred.time_str}</div>
            </div>
        `;
    }).join('');
}

function updateActivePrediction(predictions) {
    // Trouver la prédiction en attente (statut ⏳)
    const active = predictions.find(p => p.status === '⏳');
    
    const activePredictionDiv = document.getElementById('activePrediction');
    const numberEl = document.getElementById('predNumber');
    const suitEl = document.getElementById('predSuit');
    const statusEl = document.getElementById('predStatus');
    const timeEl = document.getElementById('predTime');
    
    if (!active) {
        activePredictionDiv.style.display = 'none';
        return;
    }
    
    activePredictionDiv.style.display = 'block';
    numberEl.textContent = `#${active.game_number}`;
    suitEl.textContent = getSuitDisplay(active.suit);
    statusEl.textContent = 'EN ATTENTE DU RÉSULTAT...';
    timeEl.textContent = active.time_str;
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
        document.getElementById('topWonCount').textContent = data.won_predictions;
        document.getElementById('topLostCount').textContent = data.lost_predictions;
        document.getElementById('progressHeader').textContent = 
            `${data.won_predictions + data.lost_predictions} / ${data.total_predictions}`;
        
        if (data.last_source_game) {
            document.getElementById('sourceGameNumber').textContent = '#' + data.last_source_game;
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
