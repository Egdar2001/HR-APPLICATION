document.addEventListener('DOMContentLoaded', () => {
    // 1. Dark Mode
    const themeToggleBtn = document.getElementById('themeToggle');
    const htmlElement = document.documentElement;
    const currentTheme = localStorage.getItem('theme') || 'light';
    
    htmlElement.setAttribute('data-bs-theme', currentTheme);
    updateToggleIcon(currentTheme);

    if (themeToggleBtn) {
        themeToggleBtn.addEventListener('click', () => {
            const newTheme = htmlElement.getAttribute('data-bs-theme') === 'light' ? 'dark' : 'light';
            htmlElement.setAttribute('data-bs-theme', newTheme);
            localStorage.setItem('theme', newTheme);
            updateToggleIcon(newTheme);
            if(window.taskCharts) updateChartColors(newTheme);
        });
    }

    function updateToggleIcon(theme) {
        if (!themeToggleBtn) return;
        themeToggleBtn.innerHTML = theme === 'dark' 
            ? '<i class="fa-solid fa-sun text-warning"></i>' 
            : '<i class="fa-solid fa-moon text-dark"></i>';
    }

    // 2. Notifications System
    window.markNotificationsRead = async function() {
        const badge = document.getElementById('notifBadge');
        const list = document.getElementById('notifList');
        const spinner = document.getElementById('notifSpinner');
        
        if(badge) badge.classList.add('d-none');
        if(!list || !spinner) return;
        
        spinner.classList.remove('d-none');
        try {
            const res = await fetch('/api/notifications');
            const data = await res.json();
            
            list.innerHTML = `<li><h6 class="dropdown-header border-bottom py-3 fw-bold">Notifications</h6></li>`;
            if(data.length === 0) {
                list.innerHTML += `<li><span class="dropdown-item py-3 text-muted text-center small"><i class="fa-regular fa-bell-slash fs-4 mb-2 d-block"></i>All caught up!</span></li>`;
            } else {
                data.forEach(n => {
                    const icon = n.type === 'success' ? 'fa-check text-success' : (n.type === 'danger' ? 'fa-triangle-exclamation text-danger' : 'fa-info-circle text-primary');
                    list.innerHTML += `
                        <li>
                            <div class="dropdown-item py-2 px-3 border-bottom ${n.is_read ? 'opacity-75' : 'bg-light'}">
                                <div class="d-flex align-items-start gap-2 text-wrap">
                                    <i class="fa-solid ${icon} mt-1"></i>
                                    <div>
                                        <p class="mb-0 small fw-medium">${n.message}</p>
                                        <small class="text-muted" style="font-size: 0.75rem">${n.created_at}</small>
                                    </div>
                                </div>
                            </div>
                        </li>
                    `;
                });
                // Send read request
                fetch('/api/notifications/read', { method: 'POST' });
            }
        } catch(e) { console.error(e); }
        finally { spinner.classList.add('d-none'); }
    }

    // 3. Smart Tasks & AJAX System
    const taskForm = document.getElementById('ajaxTaskForm');
    const taskList = document.getElementById('taskListContainer');
    const searchInput = document.getElementById('taskSearch');
    window.taskState = [];
    window.taskCharts = null;

    if (taskList) {
        loadTasks();

        if(taskForm) {
            taskForm.addEventListener('submit', async (e) => {
                e.preventDefault();
                const title = document.getElementById('newTaskTitle').value;
                const cat = document.getElementById('newTaskCategory').value;
                const prio = document.getElementById('newTaskPriority').value;
                const date = document.getElementById('newTaskDueDate').value;
                const btn = document.getElementById('addTaskBtn');
                
                btn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i>';
                btn.disabled = true;

                try {
                    const res = await fetch('/api/tasks', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ title, category: cat, priority: prio, due_date: date })
                    });
                    if(res.ok) {
                        taskForm.reset();
                        await loadTasks();
                        showToast('Task added successfully', 'success');
                    }
                } catch(e) {}
                finally {
                    btn.innerHTML = '<i class="fa-solid fa-plus"></i>';
                    btn.disabled = false;
                }
            });
        }
        
        if(searchInput) {
            searchInput.addEventListener('input', (e) => renderTasks(e.target.value));
        }
    }

    async function loadTasks() {
        try {
            const res = await fetch('/api/tasks');
            window.taskState = await res.json();
            renderTasks(searchInput ? searchInput.value : '');
            updateAnalytics();
        } catch(e) { console.error('Failed fetching tasks', e); }
    }

    function renderTasks(searchQuery = '') {
        if(!taskList) return;
        const emptyState = document.getElementById('taskEmptyState');
        const q = searchQuery.toLowerCase();
        
        // Remove old tasks
        document.querySelectorAll('.app-task-item').forEach(e => e.remove());
        
        const filtered = window.taskState.filter(t => t.title.toLowerCase().includes(q));
        
        if(filtered.length === 0) {
            emptyState.style.display = 'block';
        } else {
            emptyState.style.display = 'none';
            filtered.forEach(t => {
                const dueHtml = t.due_date ? `<small class="text-muted ms-2"><i class="fa-regular fa-calendar"></i> ${moment(t.due_date).format('MMM D')}</small>` : '';
                const prioColor = t.priority === 'High' ? 'danger' : (t.priority === 'Medium' ? 'warning' : 'info');
                const catColor = t.category === 'Work' ? 'primary' : (t.category === 'Urgent' ? 'danger' : 'success');
                
                const html = `
                <div class="list-group-item d-flex justify-content-between align-items-center border-0 rounded-4 py-3 mb-2 shadow-sm app-task-item transition-all ${t.is_completed ? 'bg-light opacity-75' : 'bg-white'}">
                    <div class="d-flex align-items-center gap-3 w-100">
                        <button onclick="toggleTask(${t.id}, ${t.is_completed})" class="btn btn-link p-0 text-decoration-none transition-all hover-zoom ${t.is_completed ? 'text-success' : 'text-secondary'}">
                            <i class="fa-regular ${t.is_completed ? 'fa-circle-check fs-4' : 'fa-circle fs-4'}"></i>
                        </button>
                        
                        <div class="flex-grow-1 overflow-hidden">
                            <div class="d-flex align-items-center mb-1">
                                <span class="fs-6 text-truncate d-block ${t.is_completed ? 'text-decoration-line-through text-muted' : 'fw-bold'}">${t.title}</span>
                                ${dueHtml}
                            </div>
                            <div class="d-flex gap-2">
                                <span class="badge bg-${catColor} bg-opacity-10 text-${catColor} border border-${catColor} rounded-pill font-monospace" style="font-size: 10px">${t.category}</span>
                                <span class="badge bg-${prioColor} bg-opacity-10 text-${prioColor} border border-${prioColor} rounded-pill font-monospace" style="font-size: 10px">${t.priority}</span>
                            </div>
                        </div>

                        <button onclick="deleteTask(${t.id})" class="btn btn-outline-danger btn-sm rounded-circle hover-zoom shadow-sm" title="Delete Task">
                            <i class="fa-solid fa-trash-can"></i>
                        </button>
                    </div>
                </div>`;
                taskList.insertAdjacentHTML('beforeend', html);
            });
        }
    }

    window.toggleTask = async function(id, is_comp) {
        await fetch(`/api/tasks/${id}`, {
            method: 'PATCH',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({is_completed: !is_comp})
        });
        loadTasks();
    }

    window.deleteTask = async function(id) {
        if(!confirm('Delete this task?')) return;
        await fetch(`/api/tasks/${id}`, { method: 'DELETE' });
        loadTasks();
        showToast('Task deleted', 'error');
    }

    // 4. Advanced Analytics
    function updateAnalytics() {
        const total = window.taskState.length;
        const comp = window.taskState.filter(t => t.is_completed).length;
        const pend = total - comp;

        // Stat Counter
        const statTotal = document.getElementById('stat-total');
        if(statTotal) statTotal.innerText = total;

        // Build rolling 7-day data
        const last7Days = [];
        const activityData = [0,0,0,0,0,0,0];
        
        for(let i=6; i>=0; i--) {
            last7Days.push(moment().subtract(i, 'days').format('Do MMM'));
        }
        
        window.taskState.forEach(t => {
            const tDate = moment(t.created_at).startOf('day');
            for(let i=0; i<7; i++) {
                if(tDate.isSame(moment().subtract(6-i, 'days').startOf('day'))) {
                    activityData[i]++;
                }
            }
        });

        initCharts(comp, pend, last7Days, activityData);
    }

    function initCharts(completed, pending, labels, activityLine) {
        const pieCtx = document.getElementById('taskPieChart');
        const lineCtx = document.getElementById('taskLineChart');
        if(!pieCtx || !lineCtx) return;

        const isDark = htmlElement.getAttribute('data-bs-theme') === 'dark';
        const textColor = isDark ? '#f8fafc' : '#334155';
        Chart.defaults.color = textColor;
        Chart.defaults.font.family = "'Inter', sans-serif";

        if(window.taskCharts) {
            window.taskCharts.pie.destroy();
            window.taskCharts.line.destroy();
        }

        const pieChart = new Chart(pieCtx.getContext('2d'), {
            type: 'doughnut',
            data: {
                labels: ['Completed', 'Pending'],
                datasets: [{ 
                    data: [completed, pending], 
                    backgroundColor: ['#10b981', '#f43f5e'],
                    borderWidth: 0, hoverOffset: 4
                }]
            },
            options: { responsive: true, maintainAspectRatio: false, cutout: '75%', plugins: { legend: { display: false } } }
        });

        const lineChart = new Chart(lineCtx.getContext('2d'), {
            type: 'line',
            data: {
                labels: labels,
                datasets: [{
                    label: 'Tasks Created',
                    data: activityLine,
                    borderColor: '#4f46e5',
                    backgroundColor: 'rgba(79, 70, 229, 0.2)',
                    fill: true, tension: 0.4
                }]
            },
            options: {
                responsive: true, maintainAspectRatio: false,
                plugins: { legend: { display: false } },
                scales: {
                    x: { display: false },
                    y: { beginAtZero: true, display: false }
                }
            }
        });

        window.taskCharts = { pie: pieChart, line: lineChart };
    }

    function updateChartColors(theme) {
        const isDark = theme === 'dark';
        Chart.defaults.color = isDark ? '#f8fafc' : '#334155';
        if(window.taskCharts) {
            window.taskCharts.pie.update();
            window.taskCharts.line.update();
        }
    }

    function showToast(msg, icon) {
        const Toast = Swal.mixin({
            toast: true, position: 'bottom-end', showConfirmButton: false, timer: 3000, timerProgressBar: true
        });
        Toast.fire({ icon: icon, title: msg });
    }
});
