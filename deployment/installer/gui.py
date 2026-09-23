"""MeDIAuto installer GUI; no PAT is written to a file or command line."""
import json
import os
from pathlib import Path
import queue
import shutil
import subprocess
import sys
import threading
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, simpledialog, font
from tkinter.scrolledtext import ScrolledText
from gui_contract import PREFIX, FIELDS, validate, redact, decode_log_line

ROOT=Path(__file__).resolve().parent

class Installer(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title('MeDIAuto AI — 설치 관리자')
        width=min(1040,self.winfo_screenwidth()-60);height=min(900,self.winfo_screenheight()-100)
        self.geometry(f'{width}x{height}');self.minsize(min(850,width),min(600,height))
        family='Malgun Gothic' if os.name=='nt' else 'Noto Sans CJK KR'
        for name in ('TkDefaultFont','TkTextFont','TkMenuFont','TkHeadingFont'):
            font.nametofont(name).configure(family=family,size=10)
        self.events=queue.Queue();self.process=None;self.running=False;self.values={};self.existing=False
        self.protocol('WM_DELETE_WINDOW',self.close)
        style=ttk.Style(self);style.theme_use('clam')
        self.configure(background='#f4f6fb')
        style.configure('.',background='#f4f6fb',foreground='#172b4d',font=(family,10))
        style.configure('TEntry',fieldbackground='white',padding=5)
        style.configure('TButton',padding=(12,7))
        style.configure('Title.TLabel',font=(family,22,'bold'),foreground='#3348b9')
        canvas=tk.Canvas(self,highlightthickness=0,background='#f4f6fb')
        scrollbar=ttk.Scrollbar(self,orient='vertical',command=canvas.yview)
        scrollbar.pack(side='right',fill='y');canvas.pack(side='left',fill='both',expand=True)
        canvas.configure(yscrollcommand=scrollbar.set);self.canvas=canvas
        outer=ttk.Frame(canvas,padding=20)
        content=canvas.create_window((0,0),window=outer,anchor='nw')
        outer.bind('<Configure>',lambda event:canvas.configure(scrollregion=canvas.bbox('all')))
        canvas.bind('<Configure>',lambda event:canvas.itemconfigure(content,width=event.width))
        ttk.Label(outer,text='MeDIAuto AI 설치',style='Title.TLabel').pack(anchor='w')
        ttk.Label(outer,text='GitHub 소스 · GPU 환경 · 외부 데이터 저장 · 설치 후 수동 실행').pack(anchor='w',pady=(3,12))
        row=ttk.Frame(outer);row.pack(fill='x')
        self.mode=tk.StringVar(value='docker')
        self.mode_buttons=[]
        for text,value in [('1. Docker + GitHub + 로컬 Conda 개발 환경','docker'),('2. Native + GitHub + Conda 환경','native')]:
            button=ttk.Radiobutton(row,text=text,value=value,variable=self.mode,command=self.load_existing)
            button.pack(anchor='w');self.mode_buttons.append(button)
        self.notice=tk.StringVar()
        ttk.Label(outer,textvariable=self.notice,wraplength=900,foreground='#3457a0').pack(anchor='w',pady=8)
        form=ttk.Frame(outer);form.pack(fill='x');form.columnconfigure(1,weight=1)
        self.vars={};self.entries={};self.buttons=[]
        labels={'data_root':'외부 데이터 폴더','model_path':'모델 폴더 (기존 가중치)','slide_path':'슬라이드 폴더 (빈칸 = 데이터 폴더/slides)',
                'app_port':'웹 포트','db_port':'PostgreSQL 포트','bind':'웹 바인딩 IP','repository':'GitHub 저장소','ref':'브랜치 / 태그',
                'username':'GitHub 사용자명 (공개 저장소는 빈칸)','token':'GitHub PAT (저장하지 않음)'}
        for i,key in enumerate(FIELDS):
            ttk.Label(form,text=labels[key]).grid(row=i,column=0,sticky='w',padx=(0,12),pady=4)
            v=tk.StringVar();self.vars[key]=v
            e=ttk.Entry(form,textvariable=v,show='●' if key=='token' else '');e.grid(row=i,column=1,sticky='ew',pady=4);self.entries[key]=e
            if key in ('data_root','model_path','slide_path'):
                b=ttk.Button(form,text='폴더 선택',command=lambda k=key:self.browse(k));b.grid(row=i,column=2,padx=(8,0));self.buttons.append(b)
        ttk.Label(outer,text='기본 관리자: admin / admin1234! (새 DB만)   ·   필요시 NVIDIA 드라이버 자동 설치를 시도합니다. 재부팅이 필요할 수 있습니다.').pack(anchor='w',pady=8)
        controls=ttk.Frame(outer);controls.pack(fill='x')
        self.start_button=ttk.Button(controls,text='설치 시작',command=self.start);self.start_button.pack(side='left')
        ttk.Button(controls,text='Philips SDK 라이선스 보기',command=self.license).pack(side='left',padx=8)
        ttk.Button(controls,text='로그 저장',command=self.save_log).pack(side='right')
        self.status=tk.StringVar(value='입력값을 확인한 후 설치를 시작하세요.')
        ttk.Label(outer,textvariable=self.status,wraplength=900).pack(anchor='w',pady=(10,4))
        self.progress=ttk.Progressbar(outer,mode='indeterminate');self.progress.pack(fill='x')
        self.log=ScrolledText(outer,height=13,wrap='word',state='disabled',font=('Consolas' if os.name=='nt' else 'DejaVu Sans Mono',10));self.log.pack(fill='both',expand=True,pady=(8,0))
        self.load_existing();self.poll_id=self.after(100,self.poll)
    def load_existing(self):
        if self.running:return
        defaults={'data_root':'C:/MeDIAutoData' if os.name=='nt' else '/srv/mediauto','model_path':'','slide_path':'','app_port':'18093','db_port':'55432','bind':'0.0.0.0','repository':'Leeyoungsup/Mediauto-studio_saas','ref':'main'}
        self.existing=False
        locator=ROOT/self.mode.get()/'.install-location.json'
        try:
            if locator.exists():
                data=json.loads(locator.read_text(encoding='utf-8'))
                saved=Path(data['data_root'])/'config/settings.json'
                if not saved.is_file():raise ValueError('기존 설치의 settings.json을 찾을 수 없습니다.')
                config=json.loads(saved.read_text(encoding='utf-8'))
                defaults.update({k:str(config[k]) for k in ('data_root','app_port','db_port','bind','repository','ref') if k in config})
                defaults.update(model_path=config['paths']['models'],slide_path=config['paths']['slides'])
                self.existing=True
        except (OSError,ValueError,KeyError) as exc:
            messagebox.showerror('기존 설정 확인',str(exc));self.start_button.config(state='disabled');return
        for key,value in defaults.items():self.vars[key].set(value)
        self.set_form_state(False)
        self.notice.set('기존 설치 설정을 재사용합니다. 경로·포트·브랜치는 이 화면에서 변경하지 않습니다.' if self.existing else '모델은 별도 폴더를 선택하세요. 슬라이드 폴더를 비우면 외부 데이터 폴더 아래에 저장합니다.')
    def set_form_state(self,running):
        self.start_button.config(state='disabled' if running else 'normal')
        for button in self.mode_buttons:button.config(state='disabled' if running else 'normal')
        for key,entry in self.entries.items():entry.config(state='disabled' if running or (self.existing and key not in ('username','token')) else 'normal')
        for button in self.buttons:button.config(state='disabled' if running or self.existing else 'normal')
    def browse(self,key):
        value=filedialog.askdirectory(title='폴더 선택')
        if value:self.vars[key].set(value)
    def license(self,accept=False):
        files=list((ROOT/'Philips_SDK').glob('*/EULA Research.license.txt'))
        if not files:messagebox.showerror('라이선스','번들에서 라이선스 파일을 찾을 수 없습니다.');return
        window=tk.Toplevel(self);window.title('Philips SDK 라이선스');window.geometry('800x600')
        text=ScrolledText(window,wrap='word');text.pack(fill='both',expand=True)
        text.insert('end',files[0].read_text(encoding='utf-8',errors='replace'));text.config(state='disabled')
        if accept:
            result={'answer':'no'}
            def finish(answer):result['answer']=answer;window.destroy()
            row=ttk.Frame(window);row.pack(fill='x',pady=10)
            ttk.Button(row,text='검토했고 동의합니다',command=lambda:finish('yes')).pack(side='left',padx=10)
            ttk.Button(row,text='동의하지 않음',command=lambda:finish('no')).pack(side='right',padx=10)
            window.transient(self);window.grab_set();self.wait_window(window)
            return result['answer']
    def start(self):
        if self.running:return
        values={k:v.get().strip() for k,v in self.vars.items()};values['mode']=self.mode.get()
        try:
            validate(values,self.existing)
            if not self.existing:
                for key in ('data_root','model_path','slide_path'):
                    if values[key] and not Path(values[key]).is_absolute():raise ValueError('폴더는 절대 경로로 입력하세요.')
                if not Path(values['model_path']).is_dir():raise ValueError('기존 모델 폴더를 선택하세요.')
        except ValueError as exc:messagebox.showerror('입력값 확인',str(exc));return
        self.values=values;self.running=True;self.set_form_state(True);self.progress.start(12)
        self.status.set('관리자 인증 및 설치 준비 중…');self.update_idletasks();self.canvas.yview_moveto(1)
        threading.Thread(target=self.run_worker,args=(values,),daemon=True).start()
    def run_worker(self,values):
        try:
            command=[sys.executable,'-X','utf8','-u',str(ROOT/'gui_worker.py')]
            if os.name!='nt' and os.geteuid()!=0:
                if not shutil.which('pkexec'):raise RuntimeError('pkexec가 필요합니다. polkit을 설치하거나 관리자 권한으로 GUI를 실행하세요.')
                command=['pkexec',*command]
            self.process=subprocess.Popen(command,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,encoding='utf-8',errors='replace',bufsize=1,cwd=ROOT)
            self.process.stdin.write(json.dumps(values)+'\n');self.process.stdin.flush()
            # Read bytes: native Windows tools share this pipe with the UTF-8 worker.
            for raw in iter(self.process.stdout.buffer.readline, b''):
                line=decode_log_line(raw)
                if line.startswith(PREFIX):
                    try:self.events.put(json.loads(line[len(PREFIX):]))
                    except ValueError:self.events.put({'kind':'log','text':redact(line,values)})
                else:self.events.put({'kind':'log','text':redact(line,values)})
            self.events.put({'kind':'exit','code':self.process.wait()})
        except Exception as exc:self.events.put({'kind':'log','text':redact(str(exc),values)+'\n'});self.events.put({'kind':'exit','code':1})
    def poll(self):
        while True:
            try:event=self.events.get_nowait()
            except queue.Empty:break
            kind=event['kind']
            if kind=='log':
                self.log.config(state='normal');self.log.insert('end',event['text']);self.log.see('end');self.log.config(state='disabled')
            elif kind=='phase':self.status.set(event['text'])
            elif kind=='done':self.status.set(event['text'])
            elif kind=='prompt':
                if 'SDK license' in event['text']:
                    answer=self.license(accept=True) or 'no'
                else:answer=simpledialog.askstring('설치 추가 입력',event['text'],show='●' if event.get('secret') else None,parent=self)
                try:
                    self.process.stdin.write(json.dumps({'cancel':True} if answer is None else {'answer':answer})+'\n');self.process.stdin.flush()
                except (OSError,ValueError):pass
            elif kind=='exit':
                self.running=False;self.progress.stop();self.vars['token'].set('');self.values.pop('token',None);self.load_existing()
                self.status.set('설치 완료 — 서버는 자동 실행하지 않았습니다.' if event['code']==0 else '설치 중단 — 위 로그를 확인하고 다시 실행하세요. 기존 데이터는 유지됩니다.')
                if event['code']==0:messagebox.showinfo('설치 완료','서버는 자동 실행하지 않았습니다.\nNative: native/start.bat 또는 bash native/start.sh\nDocker: docker/start.bat 또는 bash docker/start.sh\n로컬 개발: docker/start-local.bat 또는 bash docker/start-local.sh')
        self.poll_id=self.after(100,self.poll)
    def save_log(self):
        path=filedialog.asksaveasfilename(defaultextension='.log',initialfile='mediauto-install.log')
        if path:Path(path).write_text(self.log.get('1.0','end'),encoding='utf-8')
    def destroy(self):
        if hasattr(self,'poll_id'):self.after_cancel(self.poll_id)
        super().destroy()
    def close(self):
        if self.running:
            messagebox.showinfo('설치 진행 중','설치가 완료되거나 오류로 중단된 뒤 창을 닫아주세요.');return
        self.destroy()

if __name__=='__main__':Installer().mainloop()
