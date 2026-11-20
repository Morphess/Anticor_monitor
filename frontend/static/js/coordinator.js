/* KOORD: one scoped dashboard with assignments, approvals, SHA alerts and RF. */
(function () {
  'use strict';
  const $=id=>document.getElementById(id),E=Api.el,route='/api/program-routing';
  const make=(tag,a,ch)=>E(tag,a,ch);
  let programs=[],byProgram={},measures=[],executions={},assignments={},alerts=[],numberChanges=[],selectedFilter='all',flagsPanel,reportPanel;
  let currentView='programs',alertPage=0,alertTotal=0,alertUnread=0;
  let knownOrderChangeIds=null;
  const alertLimit=50;
  const expanded = new Set(); // Старе дерево: програма → розділ → захід
  const notice=(text,isError)=>{ const box=$('coord-toast');if(!box)return;
    $('coord-toast-message').textContent=text;box.classList.remove('hidden');box.dataset.kind=isError?'error':'success';setTimeout(()=>box.classList.add('hidden'),6500);
  };
  const fail=err=>{Api.showError(err);notice(err.message||String(err),true);};
  function showView(name){
    if(!['programs','risks','reports','documents'].includes(name))return;
    currentView=name;
    document.querySelectorAll('[data-coord-view]').forEach(btn=>{
      const active=btn.dataset.coordView===name;
      btn.classList.toggle('active',active);
      btn.setAttribute('aria-selected',String(active));btn.tabIndex=active?0:-1;
    });
    ['programs','risks','reports','documents'].forEach(key=>{
      const panel=$('coord-view-'+key);
      if(panel)panel.hidden=key!==name;
    });
  }
  function initTabs(){
    const buttons=[...document.querySelectorAll('[data-coord-view]')];
    buttons.forEach((btn,i)=>{
      btn.addEventListener('click',()=>showView(btn.dataset.coordView));
      btn.addEventListener('keydown',event=>{
       if(!['ArrowRight','ArrowLeft','Home','End'].includes(event.key))return;
       event.preventDefault();
       const next=event.key==='Home'?0:event.key==='End'?buttons.length-1:
         (i+(event.key==='ArrowRight'?1:-1)+buttons.length)%buttons.length;
       buttons[next].focus();showView(buttons[next].dataset.coordView);
      });
    });
    showView('programs');
  }
  function assignedSubmission(a,measure){
    const ex=ownSubmission(measure,a.user_id);
    if(!ex)return 'not_submitted';
    if(ex.status==='approved'&&!ex.document_changed&&ex.order_version_id&&ex.submitted_sha256)return 'approved';
    if(ex.status==='rejected'&&!ex.document_changed)return 'rejected';
    return 'pending';
  }
  function progressStats(rows){
    const stats={assigned:0,approved:0,pending:0,rejected:0,not_submitted:0,measures:new Set(),completed:new Set()};
    const byMeasure=new Map();
    rows.forEach(({m,a})=>{
      stats.assigned++;stats.measures.add(m.id);
      const status=assignedSubmission(a,m);stats[status]++;
      if(!byMeasure.has(m.id))byMeasure.set(m.id,[]);
      byMeasure.get(m.id).push(status);
    });
    byMeasure.forEach((statuses,mid)=>{
      if(statuses.length&&statuses.every(x=>x==='approved'))stats.completed.add(mid);
    });
    return stats;
  }
  function makeProgress(title,stats,subtitle){
    const pct=stats.assigned?100*stats.approved/stats.assigned:0;
    const card=make('div',{class:'coord-dept-progress-row'});
    const name=make('div',{},[
      make('strong',{text:title}),
      make('span',{class:'coord-progress-meta',text:subtitle||('Заходів із виконавцями: '+stats.measures.size)})
    ]);
    const data=make('div',{class:'coord-progress-data'},[
      make('strong',{text:'Погоджено '+stats.approved+' із '+stats.assigned}),
      make('div',{class:'coord-progress-track',role:'progressbar','aria-label':'Погоджено подань','aria-valuemin':'0','aria-valuemax':'100','aria-valuenow':String(Math.round(pct))},[
       make('span',{style:'width:'+pct.toFixed(2)+'%'}),
      ]),
      make('div',{class:'coord-progress-details',text:'Очікує: '+stats.pending+' · Відхилено: '+stats.rejected+' · Не подано: '+stats.not_submitted})
    ]);
    card.append(name,data);return card;
  }
  function programProgress(list,period){
    const panel=make('div',{class:'coord-dept-progress'});
    panel.appendChild(make('h3',{text:'Прогрес за підрозділами · '+Api.periodLabel(period)}));
    const container=make('div',{class:'coord-dept-progress-list'});
    // Endpoints assignment-people and executions are already limited to the KOORD branch.
    const byDepartment=new Map();let without=0;
    list.forEach(m=>{
      const people=assigned(m);
      if(!people.length)without++;
      people.forEach(a=>{
       const id=a.department_id||'';
       if(!byDepartment.has(id))byDepartment.set(id,[]);
       byDepartment.get(id).push({m,a});
      });
    });
    [...byDepartment.entries()].sort((a,b)=>Api.deptName(a[0]).localeCompare(Api.deptName(b[0]),'uk')).forEach(([id,rows])=>{
      container.appendChild(makeProgress(Api.deptName(id)||id,progressStats(rows)));
    });
    if(!byDepartment.size)container.appendChild(make('p',{class:'coord-progress-empty',text:'У цій програмі ще немає призначених виконавців.'}));
    panel.appendChild(container);
    panel.appendChild(make('p',{class:'coord-progress-empty',text:'Заходів без призначених виконавців: '+without}));
    return panel;
  }
  function measureProgress(m){
    const assignmentsHere=assigned(m);
    if(!assignmentsHere.length)return null;
    const byDepartment=new Map();
    assignmentsHere.forEach(a=>{const id=a.department_id||'';
      if(!byDepartment.has(id))byDepartment.set(id,[]);
      byDepartment.get(id).push({m,a});
    });
    const panel=make('div',{class:'coord-measure-progress'});
    const rows=make('div',{class:'coord-dept-progress-list'});
    byDepartment.forEach((items,id)=>rows.appendChild(makeProgress(Api.deptName(id)||id,progressStats(items),'Призначено виконавців: '+items.length)));
    panel.appendChild(rows);return panel;
  }
  const submissions=m=>executions[m.id]||[];
  const assigned=m=>assignments[m.id]||[];
  const ownSubmission=(m,userId)=>submissions(m).find(e=>Number(e.submitted_by_user_id)===Number(userId));
  const pending=m=>assigned(m).some(a=>{const e=ownSubmission(m,a.user_id);return e&&e.status==='pending'&&!e.document_changed;});
  const approved=m=>assigned(m).length>0&&assigned(m).every(a=>{
    const e=ownSubmission(m,a.user_id);
    return assignedSubmission(a,m)==='approved';
  });
  const isOverdue=m=>m.deadline_on&&m.deadline_on<Api.today()&&!approved(m);
  const pendingCount=()=>measures.filter(pending).length;
  const approvedCount=m=>assigned(m).filter(a=>{const e=ownSubmission(m,a.user_id);return assignedSubmission(a,m)==='approved';}).length;
  const statusLabel=m=>{
    if(approved(m))return 'Погоджено';
    if(pending(m))return 'Очікує рішення';
    if(!submissions(m).length)return assigned(m).length?'Не подано':'Не призначено';
    const n=approvedCount(m),total=assigned(m).length;
    return total ? ('Погоджено '+n+' / '+total) : 'Не призначено';
  };
  function render(){
    $('coord-total').textContent=measures.length;
    $('coord-approved').textContent=measures.filter(approved).length;
    $('coord-review-count').textContent=pendingCount();
    $('coord-overdue').textContent=measures.filter(isOverdue).length;
    ['all','approved','review','overdue','unassigned'].forEach(f=>{
      const n=$('coord-filter-'+f);if(n)n.textContent=measures.filter(m=>f==='all'||(f==='approved'&&approved(m))||(f==='review'&&pending(m))||(f==='overdue'&&isOverdue(m))||(f==='unassigned'&&!(assignments[m.id]||[]).length)).length;
    });
    $('coord-unassigned-filter').classList.remove('hidden');
    document.querySelectorAll('[data-coord-filter]').forEach(b=>{const active=b.dataset.coordFilter===selectedFilter;b.classList.toggle('active',active);b.setAttribute('aria-pressed',String(active));});
    const search=$('search').value.trim().toLowerCase();const period=$('period').value;
    const items=measures.filter(m=>{
      if(selectedFilter==='approved'&&!approved(m))return false;
      if(selectedFilter==='review'&&!pending(m))return false;
      if(selectedFilter==='overdue'&&!isOverdue(m))return false;
      if(selectedFilter==='unassigned'&&(assignments[m.id]||[]).length)return false;
      return !search||[m.id,m.description,m.program_id,Api.deptName(m.responsible_department_id),submissions(m).map(e=>e.order_number).join(' ')].join(' ').toLowerCase().includes(search);
    });
    const filterNames={all:'Усі заходи',approved:'Виконані заходи',review:'Очікують погодження',overdue:'Прострочені заходи',unassigned:'Без виконавців'};
      const host=$('programs'); host.replaceChildren();
      const inspectMode=!!search || selectedFilter!=='all';
      if(!items.length){
        host.appendChild(make('div',{class:'coord-empty'},[
          make('strong',{text:selectedFilter==='all'?'Заходів не знайдено':'Немає заходів у категорії «'+(filterNames[selectedFilter]||'')+'»'}),
          make('span',{text:'Спробуйте інший фільтр або звітний період.'}),
        ]));return;
      }
      const byPid={};items.forEach(m=>(byPid[m.program_id]||(byPid[m.program_id]=[])).push(m));
      const toggle=(key)=>{expanded.has(key)?expanded.delete(key):expanded.add(key);render();};
      const head=(text,details)=>make('button',{type:'button',class:'row-head','aria-expanded':String(details)},text);
      Object.entries(byPid).forEach(([pid,all])=>{
        const p=byProgram[pid]||{}, key='p:'+pid;
        const showProgram=inspectMode||expanded.has(key);
        const card=make('section',{class:'prog','aria-label':'Програма '+pid});
        const heading=head([
          make('span',{class:'title'},[
            make('span',{class:'code',text:pid}),
            make('span',{text:p.title||pid}),
            make('span',{class:'sub',text:p.organization_name||''}),
          ]),
          make('span',{class:'meta',text:Api.fmtDate(p.start_date)+' – '+Api.fmtDate(p.end_date)}),
          make('span',{class:'count',text:'Погоджено '+all.filter(approved).length+' / '+all.length}),
        ],showProgram);
        heading.addEventListener('click',()=>toggle(key));card.appendChild(heading);
        if(showProgram){
          const body=make('div',{class:'prog-body'});
          body.appendChild(make('div',{class:'prog-tools'},[
            make('div',{class:'small muted',text:'Код '+pid+(p.approval_reference?' · '+p.approval_reference:'')}),
            make('span',{class:'small muted',text:all.length+' заходів у програмі'}),
          ]));
          body.appendChild(programProgress(measures.filter(m=>m.program_id===pid),period));
          const bySection={};all.forEach(m=>(bySection[m.section_id]||(bySection[m.section_id]=[])).push(m));
          Object.entries(bySection).sort((x,y)=>Api.compareSections(x[0],y[0])).forEach(([sid,rows])=>{
            const sectionKey='s:'+pid+':'+sid, showSection=inspectMode||expanded.has(sectionKey);
            const section=make('section',{class:'sec'});
            const dates=rows.map(x=>x.deadline_on).filter(Boolean).sort();
            const sectionHead=head([
              make('span',{class:'title',text:Api.sectionTitle(window.coordSections||{},sid)}),
              make('span',{class:'meta',text:dates.length?'Строк до '+Api.fmtDate(dates[dates.length-1]):'Постійні / періодичні'}),
              make('span',{class:'count',text:'Погоджено '+rows.filter(approved).length+' / '+rows.length}),
            ],showSection);
            sectionHead.addEventListener('click',()=>toggle(sectionKey));section.appendChild(sectionHead);
            if(showSection){
              const secBody=make('div',{class:'sec-body'});
              rows.sort(Api.byMeasureOrder).forEach(m=>{
                const mKey='m:'+m.id,showMeasure=inspectMode||expanded.has(mKey);
                const node=make('div',{class:'measure',id:'measure-'+m.id});
                const mHead=head([
                  make('span',{class:'num',text:Api.measureNo(m)}),
                  make('span',{text:m.description}),
                  make('span',{class:'meta',text:Api.fmtDate(m.deadline_on)||m.deadline_description||'—'}),
                  make('span',{class:'role-badge '+(approved(m)?'approved':pending(m)?'pending':'none'),text:statusLabel(m)}),
                ],showMeasure);
                mHead.addEventListener('click',()=>toggle(mKey));node.appendChild(mHead);
                if(showMeasure){
                  const detail=make('div',{class:'detail coord-original-detail'});
                  const assignedRows=assigned(m);
                  const detailProgress=measureProgress(m);
                 if(detailProgress)detail.appendChild(detailProgress);
                 if(!assignedRows.length){
                    detail.appendChild(make('p',{class:'small muted',text:'Виконавців ще не призначено.'}));
                  }
                  assignedRows.forEach(a=>{
                    const ex=ownSubmission(m,a.user_id),status=Api.statusOf(ex);
                    const line=make('div',{class:'coord-executor-line'});
                    const top=make('div',{class:'coord-executor-heading'},[
                      make('strong',{text:(a.login||'Виконавець #'+a.user_id)+' · '+Api.deptName(a.department_id)}),
                      make('span',{class:'role-badge '+(ex?.status||'none'),text:ex?.document_changed?'Наказ змінено':Api.STATUS[status].label}),
                    ]);
                    line.appendChild(top);
                    if(ex){
                      line.appendChild(make('div',{class:'small muted',text:'Наказ № '+(ex.order_number||'—')+' · Подано '+(Api.fmtDate(ex.submitted_at)||'—')+' · Заявка #'+ex.id}));
                      if(ex.rejection_reason)line.appendChild(make('div',{class:'role-message error',text:'Причина відхилення: '+ex.rejection_reason}));
                      if(ex.document_changed)line.appendChild(make('div',{class:'role-message error',text:'Версію наказу змінено. Виконавець має подати наказ повторно.'}));
                    }else{
                      line.appendChild(make('div',{class:'small muted',text:'Не подано. Очікується підтвердження виконання.'}));
                    }
                    const rowActions=make('div',{class:'role-actions coord-executor-actions'});
                    const action=(label,cb,variant)=>{
                      const button=make('button',{type:'button',class:'btn '+(variant||''),text:label});
                      button.addEventListener('click',cb);rowActions.appendChild(button);
                    };
                    if(ex&&ex.document_api_path){
                      action('Переглянути наказ',()=>Api.openProtected(ex.document_api_path).catch(fail),'btn-outline-secondary');
                    }
                    if(ex&&ex.status==='pending'&&!ex.document_changed){
                      action('Погодити',()=>review(m,ex,true),'btn-success');
                      action('Відхилити',()=>review(m,ex,false),'btn-outline-danger');
                    }
                    line.appendChild(rowActions);
                    detail.appendChild(line);
                  });
                  const orphaned=submissions(m).filter(ex=>!assignedRows.some(a=>Number(a.user_id)===Number(ex.submitted_by_user_id)));
                  if(orphaned.length){
                    detail.appendChild(make('p',{class:'small muted',text:'Архів подань виконавців зі скасованими призначеннями: '+orphaned.length+' (не впливають на підсумок).'}));
                  }
                  const actions=make('div',{class:'role-actions coord-measure-bottom-actions'});
                   const assignButton=make('button',{type:'button',class:'btn',text:'Призначити виконавців'});
                  assignButton.addEventListener('click',()=>openAssign(m));actions.appendChild(assignButton);
                  detail.appendChild(actions);node.appendChild(detail);
                }
                secBody.appendChild(node);
              });section.appendChild(secBody);
            }
            body.appendChild(section);
          });card.appendChild(body);
        }
        host.appendChild(card);
      });
    }
  function jump(id){showView('programs');$('search').value=id;selectedFilter='all';render();const node=$('measure-'+id);if(node)node.scrollIntoView({behavior:'smooth',block:'center'});}
  async function load(){
    Api.showError(null);
    try {
      const mine=await Api.get(route+'/my/programs');
      const permitted=(mine||[]).filter(x=>x.access_type==='department_coordinator');
      const response=await Promise.all(permitted.map(async function(p){
        const url=route+'/programs/'+encodeURIComponent(p.id);
        const [full,rows]=await Promise.all([Api.get(url),Api.measures(p.id)]);
        return {program:full,measures:rows};
      }));
      programs=response.map(x=>x.program);byProgram=Object.fromEntries(programs.map(x=>[x.id,x]));
      measures=response.flatMap(x=>x.measures);
      window.coordSections=await Api.sections(programs.map(p=>p.id));
      // Назви лише доступних підрозділів через workflow, а не ADMIN-only довідник.
      const ownDepartments=await Promise.all(programs.map(p=>
        Api.optional(Api.get(route+'/programs/'+encodeURIComponent(p.id)+'/available-departments'))));
      ownDepartments.forEach(result=>{if(result.ok)(result.data||[]).forEach(d=>{
        Api.DEPARTMENTS[d.id]=d.name;
      });});
      const me=Api.me;
      // Посаду беремо з /api/auth/me; назву підрозділу не використовуємо замість посади.
      $('unit-name').textContent=String(me?.position||'').trim()||'Координатор підрозділу';


      $('assign-open').classList.remove('hidden');
      ['period','coord-risk-period','coord-report-period'].forEach(id=>Api.fillPeriods($(id),programs));
      if(!flagsPanel){flagsPanel=RiskFlagPanel.mount('coord-risk-panel',()=>programs,()=>$('coord-risk-period').value,jump);}
      if(!reportPanel&&$('coord-report-panel'))reportPanel=ReportPanel.mount('coord-report-panel',()=>programs,()=>$('coord-report-period').value);
      await refresh();
      if(flagsPanel)await flagsPanel.refresh();
      if(reportPanel)await reportPanel.refresh();
    }catch(err){fail(err);}
  }
  async function refresh(){
    try {
      const period=$('period').value;
      const rows=await Api.getAll('/api/executions/?period='+encodeURIComponent(period),500,'offset');
      executions={};
      rows.forEach(r=>(executions[r.measure_id]||(executions[r.measure_id]=[])).push(r));
      const results=await Promise.all(measures.map(m=>Api.optional(Api.get(route+'/measures/'+encodeURIComponent(m.id)+'/assignment-people'))));
      assignments=Object.fromEntries(measures.map((m,i)=>[m.id,results[i].data||[]]));
      render();
      await loadAlerts();
    }catch(err){fail(err);}
  }
   async function loadNumberChanges(){
     const host=$('coord-number-changes');
     if(!host)return;
     try{
       const fresh=await Api.get('/api/executions/order-number-changes?limit=50');
       if(knownOrderChangeIds!==null){
         const newer=fresh.find(item=>!knownOrderChangeIds.has(item.id));
         if(newer)notice('Виконавець змінив номер наказу: захід '+newer.measure_id+' · №'+newer.old_order_number+' → №'+newer.new_order_number);
       }
       knownOrderChangeIds=new Set(fresh.map(item=>item.id));
       numberChanges=fresh;
       renderNumberChanges();
     }catch(err){
       host.replaceChildren(make('p',{class:'role-message error',text:err.message||'Не вдалося отримати зміни номерів наказів.'}));
     }
   }
   function renderNumberChanges(){
     const host=$('coord-number-changes');if(!host)return;
     host.replaceChildren();
     if(!numberChanges.length){
       host.appendChild(make('p',{class:'small muted',text:'Замін номерів наказів ще не було.'}));return;
     }
     numberChanges.forEach(item=>{
       const card=make('article',{class:'coord-alert-item'},[
         make('strong',{text:'Захід '+item.measure_id+' · виконавець #'+item.submitted_by_user_id}),
         make('div',{class:'small muted',text:'Наказ №'+item.old_order_number+' → №'+item.new_order_number+' · '+Api.fmtDate(item.occurred_at)}),
         make('div',{class:'small muted',text:'Після зміни: очікує погодження · Поточний стан: '+(item.current_status==='pending'?'Очікує погодження':item.current_status==='approved'?'Погоджено':item.current_status==='rejected'?'Відхилено':item.current_status)})
       ]);
       const btn=make('button',{type:'button',class:'btn btn-sm',text:'Відкрити захід'});
       btn.addEventListener('click',()=>{showView('programs');jump(item.measure_id);});
       card.appendChild(btn);host.appendChild(card);
     });
   }
   async function loadAlerts(page=alertPage){
     const unread=$('coord-alert-filter')?.value==='unread';
     const qs=new URLSearchParams({skip:String(page*alertLimit),limit:String(alertLimit),unread_only:String(unread)});
     try{
      const data=await Api.get('/api/order-change-alerts/?'+qs);
      alertTotal=Number(data.total||0);alertUnread=Number(data.unread||0);
      const filtered=unread?alertUnread:alertTotal;
      alertPage=filtered?Math.min(page,Math.max(0,Math.ceil(filtered/alertLimit)-1)):0;
      if(alertPage!==page)return loadAlerts(alertPage);
      alerts=data.alerts||[];
      await loadNumberChanges();
      renderAlerts();
     }catch(err){
      const host=$('coord-alert-panel');
      if(host)host.replaceChildren(make('div',{class:'role-message error',text:err.message}));
      notice(err.message,true);
     }
   }
   function renderAlerts(){
     const host=$('coord-alert-panel'),count=$('coord-alert-count'),pager=$('coord-alert-pagination');
     host.replaceChildren();pager.replaceChildren();
     const unread=$('coord-alert-filter').value==='unread';
     const total=unread?alertUnread:alertTotal;
     count.textContent='Змін: '+alertTotal+' · Непрочитаних: '+alertUnread;
     const badge=$('coord-unread-badge');
     badge.hidden=alertUnread===0;badge.textContent=alertUnread>99?'99+':String(alertUnread);
     const list=make('div',{class:'coord-alert-list'});
     if(!alerts.length){host.appendChild(make('p',{class:'role-empty',text:unread?'Непрочитаних змін немає.':'Історія змін наказів поки порожня.'}));}
     alerts.forEach(a=>{
      const card=make('article',{class:'coord-alert-item','data-unread':String(!a.is_read)});
      const head=make('div',{class:'coord-alert-item-head'},[
        make('strong',{text:'Наказ №'+(a.order_number||a.order_id)+' · Захід '+a.measure_id}),
        make('span',{class:'small muted',text:Api.fmtDate(a.created_at)+(a.is_read?' · прочитано':' · нове')})
      ]);
      card.appendChild(head);
      card.appendChild(make('div',{class:'small muted',text:'Виконавець #'+(a.submitted_by_user_id||'—')+' · Подання #'+(a.execution_id||'—')+' · '+(a.execution_period||'—')+(a.has_approved_execution?' · На момент зміни було погоджено':'')}));
      const hashes=make('div',{class:'coord-alert-hashes'},[
        make('div',{},[
          make('span',{class:'small muted',text:'Попередня версія '+(a.previous_version_number||'—')}),
          make('code',{text:a.previous_sha256||'Хеш не надано'})
        ]),
        make('div',{},[
          make('span',{class:'small muted',text:'Нова версія '+(a.new_version_number||'—')}),
          make('code',{text:a.new_sha256||'Хеш не надано'})
        ])
      ]);
      card.appendChild(hashes);
      const actions=make('div',{class:'coord-alert-actions'});
      [['Попередній файл','previous'],['Новий файл','new']].forEach(([label,which])=>{
        const button=make('button',{type:'button',class:'btn btn-sm btn-outline-secondary',text:label});
        button.addEventListener('click',()=>Api.downloadProtected('/api/order-change-alerts/'+a.id+'/files/'+which,'order-'+a.order_id+'-'+which).catch(fail));
        actions.appendChild(button);
      });
      if(!a.is_read){
        const button=make('button',{type:'button',class:'btn btn-sm btn-dark',text:'Позначити прочитаним'});
        button.addEventListener('click',async()=>{
          button.disabled=true;
          try{await Api.post('/api/order-change-alerts/'+a.id+'/read',{});await loadAlerts();}
          catch(err){fail(err);button.disabled=false;}
        });actions.appendChild(button);
      }
      card.appendChild(actions);list.appendChild(card);
     });
     if(alerts.length)host.appendChild(list);
     if(total>alertLimit){
      const prev=make('button',{type:'button',class:'btn btn-sm',text:'← Попередні'});
      const next=make('button',{type:'button',class:'btn btn-sm',text:'Наступні →'});
      prev.disabled=alertPage===0;next.disabled=(alertPage+1)*alertLimit>=total;
      prev.addEventListener('click',()=>loadAlerts(alertPage-1));
      next.addEventListener('click',()=>loadAlerts(alertPage+1));
      pager.append(prev,make('span',{class:'small muted',text:'Сторінка '+(alertPage+1)+' із '+Math.ceil(total/alertLimit)}),next);
     }
     if(window.Notify){
      const inbox=[...measures.flatMap(m=>submissions(m).filter(e=>e.status==='pending'&&!e.document_changed).map(ex=>({lvl:'review',what:'Погодження очікує рішення',which:'Захід '+m.id+' · виконавець #'+ex.submitted_by_user_id,go:()=>jump(m.id)}))),
        ...alerts.filter(a=>!a.is_read).map(a=>({lvl:'rework',what:'Змінено файл наказу',which:'Захід '+a.measure_id,go:()=>{showView('documents');}})),
        ...numberChanges.slice(0,5).map(item=>({lvl:'review',what:'Виконавець замінив номер наказу',which:'Захід '+item.measure_id+' · №'+item.old_order_number+' → №'+item.new_order_number,go:()=>{showView('documents');}}))];
      Notify.render(inbox,'Немає нових подань або змін наказів.');
     }
   }
  function review(m,ex,approve){
    if(!ex||ex.status!=='pending'||ex.document_changed)return;
    const dlg=$('coord-review-dialog');$('coord-review-title').textContent=approve?'Погодити виконання':'Відхилити подання';
    $('coord-review-details').textContent='Захід '+m.id+' · Виконавець #'+ex.submitted_by_user_id+' · Наказ № '+ex.order_number+' · '+ex.period;
    $('coord-review-reason-label').hidden=approve;
    $('coord-review-reason').value='';$('coord-review-reason').required=!approve;
    $('coord-review-message').textContent='';dlg.dataset.execution=String(ex.id);dlg.dataset.approve=approve?'1':'0';
     dlg.dataset.version=String(ex.order_version_id||'');dlg.dataset.submittedAt=ex.submitted_at||'';dlg.showModal();
  }
  async function sendReview(ev){ev.preventDefault();const dlg=$('coord-review-dialog');
    const exId=Number(dlg.dataset.execution);if(!Number.isSafeInteger(exId)||exId<1)return;
    const approve=dlg.dataset.approve==='1';const url=Api.executionUrl(exId);
    const reason=$('coord-review-reason').value.trim();
    if(!approve&&reason.length<3){$('coord-review-message').textContent='Вкажіть причину довжиною від 3 символів.';return;}
    const btn=$('coord-review-submit');btn.disabled=true;
    try{
       const guard={expected_order_version_id:Number(dlg.dataset.version)||null,
         expected_submitted_at:dlg.dataset.submittedAt||null};
       await (approve?Api.post(url+'/approve',guard):Api.post(url+'/reject',{reason,...guard}));
      dlg.close();notice(approve?'Подання виконавця погоджено':'Подання виконавця відхилено');await refresh();}
    catch(err){$('coord-review-message').textContent=err.message;}
    finally{btn.disabled=false;}
  }
  // Призначення: два сценарії — з конкретного заходу або з глобальної кнопки.
  // Вибір усіх сутностей: пошук + список (без сторонніх JS-бібліотек).
  let editing=null,available=[],assignmentMode='global',assignmentProgramId='';
  let selectedDepartment='',selectedPerson='',executorOptions=[];
  let assignLoadToken=0,executorsLoadToken=0;
  const assignSearch={program:'',measure:'',department:'',person:''};
  const norm=value=>String(value??'').toLocaleLowerCase('uk-UA').trim();

  // Один доступний комбобокс замість окремих «Пошук» + <select>.
  // Користувач вводить текст і обирає точний варіант зі списку.
  function choiceField({id,label,options,value='',placeholder,searchPlaceholder,searchKey,onChange,disabled=false,wide=false}){
    const group=make('div',{class:'coord-assign-field'+(wide?' coord-assign-full':'')});
    const caption=make('label',{for:id,text:label});
    const combo=make('div',{class:'coord-combo'});
    const current=options.find(o=>String(o.value)===String(value));
    const input=make('input',{
      id,type:'text',class:'coord-combo-input',role:'combobox',
      autocomplete:'off',autocapitalize:'off','aria-autocomplete':'list',
      'aria-haspopup':'listbox','aria-expanded':'false',
      'aria-controls':id+'-list',placeholder:searchPlaceholder||placeholder,
    });
    input.disabled=disabled;
    input.value=assignSearch[searchKey]||current?.label||'';
    input.dataset.choiceValue=current&&(!assignSearch[searchKey]||assignSearch[searchKey]===current.label)?String(value):'';
    const toggle=make('button',{
      class:'coord-combo-toggle',type:'button',
      'aria-label':'Показати варіанти: '+label,tabindex:'-1',text:'▾',
    });
    toggle.disabled=disabled;
    const list=make('div',{id:id+'-list',class:'coord-combo-list',role:'listbox',hidden:true});
    let visible=[],activeIndex=-1;
    const close=()=>{
      list.hidden=true;
      input.setAttribute('aria-expanded','false');
      input.removeAttribute('aria-activedescendant');
      activeIndex=-1;
    };
    const highlight=()=>{
      const buttons=Array.from(list.querySelectorAll('.coord-combo-option'));
      buttons.forEach((el,i)=>{
        el.classList.toggle('is-highlighted',i===activeIndex);
        el.setAttribute('aria-selected',String(i===activeIndex));
      });
      if(activeIndex>=0&&buttons[activeIndex]){
        input.setAttribute('aria-activedescendant',buttons[activeIndex].id);
        buttons[activeIndex].scrollIntoView({block:'nearest'});
      }else input.removeAttribute('aria-activedescendant');
    };
    const choose=o=>{
      const selected=String(o.value);
      input.value=o.label;
      input.dataset.choiceValue=selected;
      assignSearch[searchKey]=o.label;
      close();
      onChange(selected);
    };
    const refreshList=(showAll=false)=>{
      const query=showAll?'':norm(input.value);
      visible=options.filter(o=>!query||norm(o.label+' '+(o.keywords||'')).includes(query));
      list.replaceChildren();
      activeIndex=-1;
      if(!visible.length){
        list.appendChild(make('div',{class:'coord-combo-empty',text:options.length?'Нічого не знайдено':'Доступних варіантів немає'}));
      }else{
        visible.slice(0,100).forEach((o,i)=>{
          const item=make('button',{
            id:id+'-opt-'+i,type:'button',role:'option',
            class:'coord-combo-option',text:o.label,'aria-selected':'false'
          });
          item.addEventListener('mousedown',e=>e.preventDefault());
          item.addEventListener('click',()=>choose(o));
          list.appendChild(item);
        });
        if(visible.length>100)list.appendChild(make('div',{class:'coord-combo-empty',text:'Уточніть пошук, щоб побачити інші результати'}));
        visible=visible.slice(0,100);
      }
      list.hidden=false;
      input.setAttribute('aria-expanded','true');
      // Список завжди під полем. Він займає місце в прокручуваній області
      // модального вікна, тому більше не перекриває попередні заходи.
      list.scrollTop=0;
      requestAnimationFrame(()=>{
        if(list.hidden||!combo.isConnected)return;
        const scroller=$('assign-body');
        if(!scroller)return;
        const viewport=scroller.getBoundingClientRect();
        const fieldRect=input.getBoundingClientRect();
        const listRect=list.getBoundingClientRect();
        // Підводимо список у видиму зону, не ховаючи поле пошуку.
        const overflow=listRect.bottom-(viewport.bottom-10);
        const safeMove=fieldRect.top-(viewport.top+8);
        if(overflow>0&&safeMove>0)
          scroller.scrollTop+=Math.min(overflow,safeMove);
      });
    };
    input.addEventListener('input',()=>{
      assignSearch[searchKey]=input.value;
      // Ручне редагування скасовує обраний варіант для перевірки при збереженні.
      input.dataset.choiceValue='';
      refreshList();
    });
    input.addEventListener('focus',()=>refreshList());
    input.addEventListener('keydown',e=>{
      if(e.key==='ArrowDown'||e.key==='ArrowUp'){
        e.preventDefault();
        if(list.hidden)refreshList();
        if(visible.length)activeIndex=(activeIndex+(e.key==='ArrowDown'?1:-1)+visible.length)%visible.length;
        highlight();
      }else if(e.key==='Enter'&&!list.hidden){
        e.preventDefault();
        if(visible.length)choose(visible[activeIndex>=0?activeIndex:0]);
      }else if(e.key==='Escape'){
        if(!list.hidden){e.preventDefault();e.stopPropagation();close();}
      }else if(e.key==='Tab')close();
    });
    toggle.addEventListener('mousedown',e=>e.preventDefault());
    toggle.addEventListener('click',()=>{
      if(list.hidden){input.focus();refreshList(true);}
      else close();
    });
    // Зміна фокуса на інше поле закриває список, але не змінює вибір.
    combo.addEventListener('focusout',()=>setTimeout(()=>{
      if(!combo.contains(document.activeElement))close();
    },0));
    combo.append(input,toggle,list);
    group.append(caption,combo);
    return group;
  }

  function assignmentMessage(message){
    $('assign-msg').textContent=message||'';
  }

  async function openAssign(measure=null){
    if(!measures.length){notice('Ще немає заходів для призначення',true);return;}
    assignmentMode=measure?'measure':'global';
    assignmentProgramId=measure?.program_id||'';
    editing=measure;
    available=[];executorOptions=[];selectedDepartment='';selectedPerson='';
    Object.keys(assignSearch).forEach(key=>assignSearch[key]='');
    assignLoadToken++;executorsLoadToken++;
    $('assign-dialog').showModal();
    assignmentMessage('');
    drawAssign();
    if(measure)await fetchAvailableDepartments(measure);
  }

  async function fetchAvailableDepartments(measure){
    const token=++assignLoadToken;
    assignmentMessage('');
    try{
      const deps=await Api.get(route+'/programs/'+encodeURIComponent(measure.program_id)+'/available-departments');
      if(token!==assignLoadToken||editing?.id!==measure.id)return;
      available=deps||[];
      available.forEach(d=>Api.DEPARTMENTS[d.id]=d.name);
      drawAssign();
    }catch(err){
      if(token!==assignLoadToken)return;
      assignmentMessage('Не вдалося завантажити підрозділи: '+(err.message||err));
      drawAssign();
    }
  }

  async function fetchExecutors(measure,departmentId){
    const token=++executorsLoadToken;
    if(!measure||!departmentId)return;
    try{
      const users=await Api.get(route+'/programs/'+encodeURIComponent(measure.program_id)
        +'/departments/'+encodeURIComponent(departmentId)+'/executors');
      if(token!==executorsLoadToken||editing?.id!==measure.id||selectedDepartment!==departmentId)return;
      executorOptions=users||[];
      drawAssign();
    }catch(err){
      if(token!==executorsLoadToken)return;
      executorOptions=[];
      drawAssign();
      assignmentMessage('Не вдалося завантажити виконавців: '+(err.message||err));
    }
  }

  function drawAssign(){
    const box=$('assign-body');box.replaceChildren();
    const fields=make('div',{class:'coord-assign-fields'});

    if(assignmentMode==='global'){
      fields.appendChild(choiceField({
        id:'assign-program',label:'Оберіть програму',searchKey:'program',wide:true,
        options:programs.map(p=>({value:p.id,label:p.id+' · '+(p.title||p.id),keywords:p.organization_name||''})),
        value:assignmentProgramId,placeholder:'Оберіть програму',searchPlaceholder:'Пошук програми за кодом або назвою',
        onChange:pid=>{
          assignmentProgramId=pid;editing=null;available=[];executorOptions=[];
          selectedDepartment='';selectedPerson='';
          assignSearch.measure='';assignSearch.department='';assignSearch.person='';
          assignLoadToken++;executorsLoadToken++;
          assignmentMessage('');drawAssign();
        }
      }));
      if(assignmentProgramId){
        const choices=measures.filter(m=>m.program_id===assignmentProgramId);
        fields.appendChild(choiceField({
          id:'assign-measure-picker',label:'Оберіть захід',wide:true,searchKey:'measure',
          options:choices.map(m=>({value:m.id,label:m.id+' · '+m.description,keywords:m.section_id+' '+m.sequence_number})),
          value:editing?.id||'',placeholder:'Оберіть захід',searchPlaceholder:'Пошук заходу за кодом або описом',
          onChange:id=>{
            editing=choices.find(m=>m.id===id)||null;
            available=[];executorOptions=[];selectedDepartment='';selectedPerson='';
            assignSearch.department='';assignSearch.person='';
            assignLoadToken++;executorsLoadToken++;
            assignmentMessage('');drawAssign();
            if(editing)fetchAvailableDepartments(editing);
          }
        }));
      }
    }

    if(editing){
      const depOptions=available.map(d=>({value:d.id,label:d.name+' ('+d.id+')'}));
      fields.appendChild(choiceField({
        id:'assign-department',label:'Підрозділ',searchKey:'department',
        options:depOptions,value:selectedDepartment,
        placeholder:'Оберіть підрозділ',searchPlaceholder:'Пошук за назвою або кодом підрозділу',
        disabled:!available.length,
        onChange:id=>{
          selectedDepartment=id;selectedPerson='';executorOptions=[];
          assignSearch.person='';executorsLoadToken++;
          assignmentMessage('');drawAssign();
          if(id)fetchExecutors(editing,id);
        }
      }));
      const unassigned=executorOptions.filter(u=>
        !assigned(editing).some(a=>Number(a.user_id)===Number(u.id)));
      fields.appendChild(choiceField({
        id:'assign-person',label:'Виконавець',searchKey:'person',
        options:unassigned.map(u=>({
          value:u.id,label:u.login+(u.position?' · '+u.position:'')+' (#'+u.id+')',
          keywords:u.id+' '+(u.position||'')
        })),value:selectedPerson,
        placeholder:'Оберіть виконавця',searchPlaceholder:'Пошук за логіном, ID або посадою',
        disabled:!selectedDepartment||!unassigned.length,
        onChange:id=>{selectedPerson=id;assignmentMessage('');}
      }));
    }
    box.append(fields);

    const hint=make('p',{class:'coord-assign-hint small muted',role:'status'});
    if(assignmentMode==='global'&&!assignmentProgramId)hint.textContent='Спочатку оберіть програму.';
    else if(!editing)hint.textContent='';
    else if(!available.length)hint.textContent='Завантаження підрозділів або немає доступних підрозділів.';
    else if(!selectedDepartment)hint.textContent='Оберіть підрозділ, щоб побачити доступних виконавців.';
    else if(!executorOptions.length)hint.textContent='У підрозділі немає доступних виконавців або список ще завантажується.';
    else if(executorOptions.every(u=>assigned(editing).some(a=>Number(a.user_id)===Number(u.id))))
      hint.textContent='Усі виконавці цього підрозділу вже призначені на захід.';
    else hint.textContent='Можна призначити кількох виконавців по черзі.';
    hint.hidden=!hint.textContent;
    box.append(hint);

    if(!editing)return;
    const current=make('div',{class:'coord-current-assignments'});
    current.appendChild(make('h3',{text:'Чинні призначення'}));
    const assignmentsHere=assigned(editing);
    if(!assignmentsHere.length)current.appendChild(make('p',{class:'small muted',text:'Поки немає призначень.'}));
    assignmentsHere.forEach(a=>{
      const row=make('div',{class:'coord-current-assignment'},[
        make('span',{text:(a.login||'Користувач #'+a.user_id)+' · '+Api.deptName(a.department_id)})
      ]);
      const revoke=make('button',{type:'button',class:'btn btn-sm btn-outline-danger',text:'Відкликати'});
      revoke.addEventListener('click',async()=>{
        if(!confirm('Відкликати призначення користувача #'+a.user_id+'?'))return;
        revoke.disabled=true;
        try{
          await Api.del(route+'/measures/'+editing.id+'/assign/'+a.user_id);
          notice('Призначення відкликано');await refresh();
          selectedPerson='';assignSearch.person='';
          if(selectedDepartment)await fetchExecutors(editing,selectedDepartment);
          else drawAssign();
        }catch(err){revoke.disabled=false;fail(err);}
      });
      row.appendChild(revoke);current.appendChild(row);
    });
    box.append(current);
  }

  async function saveAssign(){
    if(!editing){assignmentMessage('Спочатку оберіть програму та захід.');return;}
    const validChoice=(id,value)=>$(id)?.dataset.choiceValue===String(value);
    if(assignmentMode==='global'&&(!validChoice('assign-program',assignmentProgramId)||!validChoice('assign-measure-picker',editing.id))){
      assignmentMessage('Виберіть програму та захід із запропонованого списку.');return;
    }
    if(!selectedDepartment||!selectedPerson||!validChoice('assign-department',selectedDepartment)||!validChoice('assign-person',selectedPerson)){
      assignmentMessage('Виберіть підрозділ і виконавця із запропонованого списку.');return;
    }
    const saveButton=$('assign-save');saveButton.disabled=true;
    try{
      await Api.post(route+'/measures/'+encodeURIComponent(editing.id)+'/assign',{
        department_id:selectedDepartment,user_id:Number(selectedPerson)
      });
      notice('Виконавця призначено');
      selectedPerson='';assignSearch.person='';
      await refresh();
      await fetchExecutors(editing,selectedDepartment);
    }catch(err){assignmentMessage(err.message||String(err));}
    finally{saveButton.disabled=false;}
  }
  async function init(){if(!await Api.requireRole('KOORD'))return;
     initTabs();
     $('coord-risk-period').addEventListener('change',()=>flagsPanel?.refresh().catch(fail));
     $('coord-report-period').addEventListener('change',()=>reportPanel?.refresh().catch(fail));
     $('coord-alert-filter').addEventListener('change',()=>loadAlerts(0));
     $('coord-alert-refresh').addEventListener('click',()=>loadAlerts());
    ['search'].forEach(id=>$(id).addEventListener('input',render));
    $('period').addEventListener('change',refresh);
    $('coord-refresh').addEventListener('click',load);
    document.querySelectorAll('[data-coord-filter]').forEach(btn=>btn.addEventListener('click',()=>{
      selectedFilter=btn.dataset.coordFilter;
      $('search').value='';render();
    }));
    $('coord-toast-close').addEventListener('click',()=>$('coord-toast').classList.add('hidden'));
    $('coord-clear-search').addEventListener('click',()=>{$('search').value='';render();});
    $('assign-open').addEventListener('click',()=>openAssign(null));
    $('assign-cancel').addEventListener('click',()=>$('assign-dialog').close());
    $('assign-close').addEventListener('click',()=>$('assign-dialog').close());
    $('assign-save').addEventListener('click',saveAssign);
    $('coord-review-form').addEventListener('submit',sendReview);
    $('coord-review-cancel').addEventListener('click',()=>$('coord-review-dialog').close());
    await load();
    setInterval(async()=>{
      if(document.hidden)return;
      try{
        const rows=await Api.getAll('/api/executions/?period='+encodeURIComponent($('period').value),500,'offset');
        executions={};
        rows.forEach(r=>(executions[r.measure_id]||(executions[r.measure_id]=[])).push(r));
        render();
        await loadNumberChanges();
        renderAlerts();
      }catch(err){/* periodic failures do not interrupt manual controls */}
    },45000);
  }
  init();
})();
