/* Reusable Risk Flags panel for MAIN_KOORD / KOORD. Server-side scope and rules. */
(function () {
  'use strict';
  const e = Api.el;
  function node(tag, attrs, children) { return e(tag, attrs, children); }
  const FLAGS = Api.FLAGS;
  window.RiskFlagPanel = {
    mount: function (targetId, getPrograms, getPeriod, onMeasureClick) {
      const host = document.getElementById(targetId);
      if (!host) return null;
      let rows = [], problem = '', modeNote = '';
      const head = node('div', { class: 'role-toolbar' });
      const programLabel = node('label', {}, [node('span', {class:'role-form-label', text:'Програма'} )]);
      const prog = node('select', {class:'role-field', 'aria-label':'Програма Risk Flags'});
      programLabel.appendChild(prog);
      const codeLabel = node('label', {}, [node('span', {class:'role-form-label', text:'Тип сигналу'})]);
      const code = node('select', {class:'role-field', 'aria-label':'Тип Risk Flag'});
      code.appendChild(node('option', {value:'', text:'Усі сигнали'}));
      Object.keys(FLAGS).forEach(function (key) { code.appendChild(node('option', {value:key,text:key+' — '+FLAGS[key]})); });
      codeLabel.appendChild(code);
      const reload = node('button', {class:'btn btn-outline-secondary',type:'button',text:'Оновити сигнали'});
      const note = node('p', {class:'small muted', role:'status', 'aria-live':'polite'});
      const list = node('div', {class:'role-risk-list', 'aria-live':'polite'});
      head.append(programLabel,codeLabel,reload); host.replaceChildren(head,note,list);
      const options = function () {
        const programs = getPrograms() || [];
        const before = prog.value;
        prog.replaceChildren(node('option',{value:'',text:'Оберіть програму'}));
        programs.forEach(function (p) { prog.appendChild(node('option',{value:p.id,text:(p.title||p.id)})); });
        if (programs.some(function (p) {return p.id===before;})) prog.value=before;
        else if(programs.length)prog.value=programs[0].id;
      };
      const render = function () {
        list.replaceChildren();
        if (problem) { list.appendChild(node('p',{class:'role-message error',text:problem})); return; }
        note.textContent = modeNote || 'Сигнал обчислюється на сервері за поточним станом даних.';
        const shown = rows.filter(function (f) {return !code.value || f.code===code.value;});
        if (!shown.length) {list.appendChild(node('p',{class:'role-empty',text: rows.length ? 'Немає сигналів за вибраним типом.' : 'Сигналів за вибраною програмою та періодом немає.'}));return;}
        shown.forEach(function (f) {
          const card=node('article',{class:'role-risk-item'});
          card.appendChild(node('strong',{text:f.code+' · '+(FLAGS[f.code]||f.message)}));
          card.appendChild(node('span',{class:'role-muted',text:(Api.OBJECT_TYPES[f.object_type]||f.object_type)+' '+f.object_id+' · '+f.period}));
          card.appendChild(node('p',{text:f.explanation||f.message}));
          if (f.object_type==='zakhid' && typeof onMeasureClick==='function') {
            const b=node('button',{type:'button',class:'btn btn-sm btn-outline-secondary',text:'Відкрити захід'});
            b.addEventListener('click',function(){onMeasureClick(f.object_id);});card.appendChild(b);
          }
          list.appendChild(card);
        });
      };
      const load=async function () {
        if (!prog.value) { rows=[];render();return; }
        reload.disabled=true;note.textContent='Завантажуємо сигнали…';problem='';modeNote='';
        try {
          const result=await Api.riskFlags(prog.value,getPeriod(),null);
          if(!result.ok){ problem=(result.error&&result.error.message)||result.reason||'Не вдалося завантажити Risk Flags'; rows=[]; }
          else{rows=result.data||[];modeNote=result.note||'Знайдено сигналів: '+rows.length;}
        } catch(err){problem=err.message; rows=[];}
        finally{reload.disabled=false;render();}
      };
      prog.addEventListener('change',load);code.addEventListener('change',render);reload.addEventListener('click',load);
      return {refresh: async function () {options();await load();},setProgram:function(id){prog.value=id;return load();}};
    }
  };
})();
