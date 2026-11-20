/* Reusable portal reporting panel for MAIN_KOORD and KOORD. */
(function () {
  'use strict';
  const make = Api.el;
  const qs = (obj) => new URLSearchParams(obj).toString();
  window.ReportPanel = {
    mount: function (id, programsFn, periodFn) {
      const root = document.getElementById(id);
      if (!root) return null;
      const controls = make('div', {class:'role-toolbar report-toolbar'});
      const label = make('label', {class:'role-form-label report-program-field'});
      label.appendChild(make('span', {text:'Програма'}));
      const select = make('select',{class:'role-field','aria-label':'Програма для звітності'});
      label.appendChild(select);
      const preview = make('button',{type:'button',class:'btn btn-outline-secondary',text:'Попередній перегляд'});
      const generate = make('button',{type:'button',class:'btn btn-dark',text:'Сформувати версію'});
      const reload = make('button',{type:'button',class:'btn btn-outline-secondary',text:'Оновити список'});
      const note = make('p',{class:'small muted report-panel-note','aria-live':'polite'});
      const summary = make('div',{class:'mb-3','aria-live':'polite'});
      const list = make('div',{class:'role-report-list','aria-live':'polite'});
      const actionsBar = make('div', {class:'report-toolbar-actions'});
      actionsBar.append(preview,generate,reload);
      controls.append(label,actionsBar);
      const edits = make('div',{class:'mb-3', 'aria-live':'polite'});
      root.replaceChildren(controls,note,summary,edits,list);
      let active = 0;
      const notesByMeasure = new Map();
      let editableProgram = '';
      let editablePeriod = '';
      function clearReportEdits() {
        notesByMeasure.clear();
        edits.replaceChildren();
        editableProgram = '';
        editablePeriod = '';
      }
      function patchNote(measureId, key, value) {
        const note = notesByMeasure.get(measureId) || {measure_id:measureId};
        note[key] = value;
        notesByMeasure.set(measureId, note);
      }
      function textInput(labelText, initialValue, handler, multiline) {
        const container = make('label',{class:'d-block mb-2'});
        container.appendChild(make('span',{class:'small text-secondary d-block mb-1',text:labelText}));
        const field = multiline
          ? make('textarea',{class:'form-control form-control-sm',rows:2})
          : make('input',{class:'form-control form-control-sm',type:labelText==='Фактична дата виконання'?'date':'number'});
        field.value = initialValue == null ? '' : String(initialValue);
        field.addEventListener('input',()=>handler(field.value));
        container.appendChild(field);
        return container;
      }
      function renderCoordinatorEdits(data) {
        clearReportEdits();
        editableProgram = data.program_id;
        editablePeriod = data.period;
        const all = (data.sections || []).flatMap(s=>(s.measures||[]).map(m=>({...m, section_number:s.number})));
        const wrapper=make('div',{class:'role-card'});
        wrapper.appendChild(make('h3',{text:'Дані звіту — заповнює координатор'}));
        wrapper.appendChild(make('p',{class:'small muted',text:'Додайте фактичні результати, дати та показники. Це не змінює подання виконавців і не погоджує накази. Натисніть «Сформувати версію», щоб зафіксувати ці дані в новому звіті.'}));
        all.forEach(m=>{
          const section=make('details',{class:'border-bottom py-2'});
          section.appendChild(make('summary',{text:(m.measure_id||'')+' · '+(m.measure_description||'Захід')}));
          const fields=make('div',{class:'pt-2'});
          fields.appendChild(make('p',{class:'small muted',text:'Стан за погодженнями: '+m.execution_status+(m.approved_by_coordinator?' · Погоджено':' · Не всі виконання погоджено')}));
          if(m.approved_by_coordinator && m.execution_status!=='Строк виконання заходу не настав'){
            const choice = make('select',{class:'form-select form-select-sm mb-2'});
            ['Виконано','Частково виконано','Не виконано'].forEach(t=>choice.appendChild(make('option',{value:t,text:t})));
            choice.value = ['Виконано','Частково виконано','Не виконано'].includes(m.execution_status)?m.execution_status:'Не виконано';
            choice.addEventListener('change',()=>patchNote(m.measure_id,'execution_status',choice.value));
            fields.appendChild(make('span',{class:'small text-secondary d-block mb-1',text:'Фактичний стан виконання'}));
            fields.appendChild(choice);
          }
          fields.appendChild(textInput('Опис результату або пояснення причин невиконання',m.result_description||'',
            v=>patchNote(m.measure_id,'result_description',v),true));
          if(m.approved_by_coordinator){
            fields.appendChild(textInput('Фактична дата виконання',m.factual_date||'',
              v=>patchNote(m.measure_id,'factual_date',v||null),false));
          }
          if(m.section_number===3){
            fields.appendChild(textInput('Кількість осіб на навчанні',m.participants_count,
              v=>patchNote(m.measure_id,'participants_count',v===''?null:Number(v)),false));
          } else if(m.indicator_target!=null){
            fields.appendChild(textInput('Фактичний показник',m.indicator_actual,
              v=>patchNote(m.measure_id,'indicator_actual',v===''?null:Number(v)),false));
          }
          section.appendChild(fields);
          wrapper.appendChild(section);
        });
        edits.replaceChildren(wrapper);
      }
      function fillPrograms() {
        const current = select.value;
        const programs = programsFn() || [];
        select.replaceChildren(make('option',{value:'',text:'Оберіть програму'}));
        programs.forEach(p=>select.appendChild(make('option',{value:p.id,text:p.title||p.id})));
        select.value = programs.some(p=>p.id===current) ? current : (programs[0]?.id||'');
      }
      function info(msg, error) {
        note.textContent = msg||'';
        note.className='small report-panel-note '+(error?'role-message error':'muted');
      }
      function statusLabel(value) {return ({draft:'Чернетка',generated:'Сформовано',submitted:'Подано'})[value] || value;}
      function present(data, title) {
        summary.replaceChildren();
        const s=data.summary||{};
        const block=make('div',{class:'role-card'});
        block.appendChild(make('h3',{text:title+' · '+Api.periodLabel(data.period)}));
        block.appendChild(make('p',{class:'small muted',text:(data.is_preliminary?'Попередній звіт':'Підсумковий період')+' · дата зрізу '+(data.as_of||'—')}));
        const values=[['Усього',s.total],['Виконано',s.completed],['Частково',s.partial],['Не виконано',s.not_completed],['Не погоджено',s.unapproved]];
        const numbers=make('div',{class:'row g-2'});
        values.forEach(([name,value])=>{const col=make('div',{class:'col-6 col-lg-3'}),box=make('div',{class:'border rounded p-2 h-100'});
          box.append(make('span',{class:'small text-secondary d-block',text:name}),make('strong',{class:'fs-5',text:String(value??0)}));col.appendChild(box);numbers.appendChild(col);});
        block.appendChild(numbers);
        const all=(data.sections||[]).flatMap(part=>(part.measures||[]).flatMap(m=>(m.warnings||[]).map(w=>({id:m.measure_id,warning:w}))));
        if(all.length){const details=make('details',{class:'mt-3'});
          details.appendChild(make('summary',{text:'Зауваження ('+all.length+')'}));
          const ul=make('ul',{class:'list-group list-group-flush'});
          all.slice(0,70).forEach(w=>ul.appendChild(make('li',{class:'list-group-item',text:w.id+' — '+w.warning})));
          details.appendChild(ul);block.appendChild(details);
        }
        summary.appendChild(block);
      }
      async function renderList(){
        if(!select.value){list.replaceChildren(make('p',{class:'role-empty',text:'Немає доступних програм.'}));return;}
        const token=++active;
        info('Завантаження версій звіту…');
        const url='/api/reports/?'+qs({program_id:select.value,period:periodFn(),limit:100});
        try{
          const rows=await Api.get(url);
          if(token!==active)return;
          info('Історія збережених версій. Дані вже сформованого звіту не змінюються.');
          list.replaceChildren();
          if(!rows.length){list.appendChild(make('p',{class:'role-empty',text:'Збережених звітів ще немає.'}));return;}
          rows.slice().reverse().forEach(report=>{
            const card=make('div',{class:'report-version-row'});
            const body=make('div',{class:'report-version-summary'});body.append(make('strong',{text:'Версія '+report.version}),make('p',{class:'small muted m-0',text:statusLabel(report.status)+' · '+Api.periodLabel(report.period)+' · ID '+report.id}));
            const actions=make('div',{class:'report-version-actions'});
            const view=make('button',{type:'button',class:'btn btn-sm btn-outline-secondary',text:'Переглянути'});
            view.addEventListener('click',async()=>{try{info('Завантаження вмісту…');const payload=await Api.get('/api/reports/'+report.id+'/content');clearReportEdits();present(payload,'Звіт №'+report.id);info('Вміст збереженої версії.');}catch(err){info(err.message,true);}});
            actions.appendChild(view);
            if(report.status!=='draft'){
              const pdf=make('button',{type:'button',class:'btn btn-sm btn-outline-primary',text:'PDF'});
              pdf.addEventListener('click',()=>Api.downloadProtected('/api/reports/'+report.id+'/download.pdf','report-'+report.id+'-'+report.period+'.pdf').catch(err=>info(err.message,true)));
              const csv=make('button',{type:'button',class:'btn btn-sm btn-outline-secondary',text:'CSV'});
              csv.addEventListener('click',()=>Api.downloadProtected('/api/reports/'+report.id+'/download.csv','report-'+report.id+'.csv').catch(err=>info(err.message,true)));
              const html=make('button',{type:'button',class:'btn btn-sm btn-outline-secondary',text:'HTML для друку'});
              html.addEventListener('click',()=>Api.downloadProtected('/api/reports/'+report.id+'/print','report-'+report.id+'.html').catch(err=>info(err.message,true)));
              actions.append(pdf,csv,html);
              if(report.status==='generated'){
                const send=make('button',{type:'button',class:'btn btn-sm btn-primary',text:'Позначити як поданий'});
                send.addEventListener('click',async()=>{
                  if(!confirm('Ви вже подали цей звіт через офіційний портал НАЗК? Ця кнопка лише фіксує статус у Anticor_monitor; передавання до НАЗК НЕ відбувається.'))return;
                  send.disabled=true;
                  try{await Api.patch('/api/reports/'+report.id,{status:'submitted'});await renderList();info('Звіт №'+report.id+' позначено як поданий у Anticor_monitor. До НАЗК файл автоматично не передано.');}
                  catch(err){info(err.message,true);send.disabled=false;}
                });actions.appendChild(send);
              }
            }
            card.append(body,actions);list.appendChild(card);
          });
        }catch(err){if(token===active){info(err.message,true);list.replaceChildren();}}
      }
      preview.addEventListener('click',async()=>{
        if(!select.value)return;
        preview.disabled=true;info('Розрахунок попереднього звіту…');
        try{const data=await Api.get('/api/reports/preview?'+qs({program_id:select.value,period:periodFn()}));present(data,'Попередній перегляд');renderCoordinatorEdits(data);info('Відредагуйте звітні дані нижче або сформуйте версію без правок.');}
        catch(err){info(err.message,true);}finally{preview.disabled=false;}
      });
      generate.addEventListener('click',async()=>{
        if(!select.value)return;
        if(!confirm('Сформувати нову незмінну версію звіту для '+Api.periodLabel(periodFn())+'?'))return;
        generate.disabled=true;info('Формування нової версії…');
        try{const payload = (editableProgram===select.value && editablePeriod===periodFn()) ? {overrides:Array.from(notesByMeasure.values())} : {overrides:[]}; const report=await Api.post('/api/reports/auto-generate?'+qs({program_id:select.value,period:periodFn()}),payload);clearReportEdits();info('Створено звіт №'+report.id+' · версія '+report.version);await renderList();}
        catch(err){info(err.message,true);}finally{generate.disabled=false;}
      });
      select.addEventListener('change',()=>{clearReportEdits();summary.replaceChildren();renderList();});
      reload.addEventListener('click',renderList);
      return {refresh:async function(){fillPrograms();await renderList();}};
    }
  };
})();
