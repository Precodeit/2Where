import flet as ft
import json
import os
import base64
import warnings
import urllib.parse 

# העלמת אזהרות ה-Deprecation של Flet כדי לשמור על קונסול נקי
warnings.filterwarnings("ignore", category=DeprecationWarning)

class AppBackend:
    def __init__(self):
        self.users_file = 'users.json'
        self.activities_file = 'activities.json'
        self.users_db = self.load_users()
        self.activities_db = self.load_activities()
        self.last_registered_user = ""
        self.current_event = None

        self.user_session = {"name": "", "budget": 1000, "area": "אילת", "people_count": 4, "sort_by": "default"}
        self.people_map = {'1-2': 2, '3-5': 4, '5-7': 6, '10+': 12}
        self.budget_options = {'חינם': 0, ' עד 50 ש"ח': 50, 'עד 100 ש"ח': 100, 'ללא הגבלה': 1000}
        self.areas = ['אילת', 'דרום', 'מרכז', 'צפון']

    def load_users(self):
        if os.path.exists(self.users_file):
            with open(self.users_file, 'r', encoding='utf-8') as f:
                loaded_users = json.load(f)
                for username, data in loaded_users.items():
                    if isinstance(data, str):
                        loaded_users[username] = {"password": data, "email": f"{username}@example.com", "avatar": "", "preferences": {}, "favorites": []}
                    else:
                        if "avatar" not in data: data["avatar"] = ""
                        if "preferences" not in data: data["preferences"] = {}
                        if "favorites" not in data: data["favorites"] = []
                return loaded_users
        else:
            default_users = {"admin": {"password": "1234", "email": "admin@eilat.co.il", "avatar": "", "preferences": {}, "favorites": []}}
            with open(self.users_file, 'w', encoding='utf-8') as f:
                json.dump(default_users, f)
            return default_users

    def load_activities(self):
        if os.path.exists(self.activities_file):
            with open(self.activities_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        return {}

    def save_users(self):
        with open(self.users_file, 'w', encoding='utf-8') as f:
            json.dump(self.users_db, f)

    def login(self, identifier, password):
        matched_user = None
        if identifier in self.users_db and self.users_db[identifier]["password"] == password:
            matched_user = identifier
        else:
            for username, data in self.users_db.items():
                if data["email"] == identifier and data["password"] == password:
                    matched_user = username
                    break

        if matched_user:
            self.user_session["name"] = matched_user
            prefs = self.users_db[matched_user].get("preferences", {})
            if prefs:
                self.user_session.update(prefs)
            return True
        return False

    def register(self, username, email, password):
        if username in self.users_db: return False
        for data in self.users_db.values():
            if data["email"] == email: return False
        self.users_db[username] = {"password": password, "email": email, "avatar": "", "preferences": {}, "favorites": []}
        self.save_users()
        self.last_registered_user = username
        return True

    def toggle_favorite(self, activity_name):
        username = self.user_session["name"]
        if username and username != "אורח":
            favs = self.users_db[username]["favorites"]
            if activity_name in favs:
                favs.remove(activity_name)
            else:
                favs.append(activity_name)
            self.save_users()

    def update_avatar(self, url):
        username = self.user_session["name"]
        if username and username != "אורח":
            self.users_db[username]["avatar"] = url
            self.save_users()

    def update_preferences(self, budget, area, people_count):
        username = self.user_session["name"]
        if username and username != "אורח":
            prefs = {"budget": budget, "area": area, "people_count": people_count}
            self.users_db[username]["preferences"] = prefs
            self.save_users()
            self.user_session.update(prefs)

    def filter_data(self):
        filtered = []
        for activity in self.activities_db.values():
            if activity['location'] == self.user_session['area'] and activity['price'] <= self.user_session['budget']:
                if self.user_session['people_count'] in activity['people_range']:
                    filtered.append(activity)
        if self.user_session['sort_by'] == 'price_asc':
            filtered.sort(key=lambda x: x['price'])
        elif self.user_session['sort_by'] == 'price_desc':
            filtered.sort(key=lambda x: x['price'], reverse=True)
        return filtered

def main(page: ft.Page):
    page.title = "מערכת אילת"
    page.rtl = True
    page.theme_mode = ft.ThemeMode.LIGHT
    page.fonts = {"Rubik": "https://fonts.googleapis.com/css2?family=Rubik:wght@400;600;800&display=swap"}
    page.theme = ft.Theme(font_family="Rubik")
    page.horizontal_alignment = ft.CrossAxisAlignment.CENTER
    page.window.width = 450
    page.window.height = 800
    
    # --- CRITICAL FIX 1: Remove all page borders so the background touches the very edges ---
    page.padding = 0
    page.spacing = 0

    backend = AppBackend()

    # This container holds your foreground app buttons, menus, and forms
    content_container = ft.Container(expand=True, padding=10)

    # --- CRITICAL FIX 2: Create a layout that forces the image to stretch and stay frozen ---
    # Layer 1: The Background Image (Stretches to 100% of the screen limits)
    bg_layer = ft.Column(
        controls=[
            ft.Row(
                controls=[ft.Image(src="bg.jpg", fit="cover", expand=True)],
                expand=True
            )
        ],
        expand=True
    )

    # Layer 2: The Stack (Puts the frozen background on the bottom, and the safe, scrolling content on top)
    main_layout = ft.Stack(
        controls=[
            bg_layer, # Bottom layer (Ignores notch, covers glass)
            ft.SafeArea(content=content_container, expand=True) # Top layer (Protects buttons from notch)
        ],
        expand=True
    )
    # -----------------------------------------------------------------------------------------

    # --- FILE PICKER LOGIC ---
    async def on_avatar_upload(e):
        try:
            files = await ft.FilePicker().pick_files(allow_multiple=False, with_data=True)
            if files and len(files) > 0:
                f = files[0]
                mime_type = "image/jpeg"
                if getattr(f, "name", "").lower().endswith(".png"):
                    mime_type = "image/png"
                
                file_bytes = None
                if getattr(f, "content", None):
                    file_bytes = f.content
                elif getattr(f, "path", None):
                    with open(f.path, "rb") as image_file:
                        file_bytes = image_file.read()
                
                if file_bytes:
                    encoded_string = base64.b64encode(file_bytes).decode('utf-8')
                    data_url = f"data:{mime_type};base64,{encoded_string}"
                    backend.update_avatar(data_url)
                    render("personal_area")
        except Exception as ex:
            print(f"Error picking file: {ex}")
    # -------------------------

    def render(screen_name):
        # Push the new screen into the protected content container
        content_container.content = build_screen(screen_name)
        page.update()

    def get_header():
        user_name = backend.user_session.get("name", "אורח")
        avatar_url = ""
        if user_name and user_name != "אורח":
            avatar_url = backend.users_db.get(user_name, {}).get("avatar", "")

        if avatar_url:
            avatar = ft.CircleAvatar(foreground_image_url=avatar_url, radius=22)
        else:
            first_letter = user_name[0].upper() if user_name else "U"
            avatar = ft.CircleAvatar(content=ft.Text(first_letter, color=ft.Colors.WHITE), bgcolor="#4B0082", radius=22)

        def handle_menu(e):
            action = e.control.data
            if action == "logout":
                backend.user_session["name"] = ""
                render("welcome")
            elif action == "personal_area":
                render("personal_area")
            elif action == "search_screen":
                render("search_screen")

        menu = ft.PopupMenuButton(
            content=avatar,
            items=[
                ft.PopupMenuItem(content=ft.Text("חזרה לחיפוש"), data="search_screen", on_click=handle_menu),
                ft.PopupMenuItem(content=ft.Text("אזור אישי"), data="personal_area", on_click=handle_menu),
                ft.PopupMenuItem(content=ft.Text("החברים שלי"), data="friends", on_click=handle_menu),
                ft.PopupMenuItem(content=ft.Text("התנתקות"), data="logout", on_click=handle_menu),
            ]
        )

        logo = ft.Container(
            content=ft.Text("מערכת אילת", weight=ft.FontWeight.W_800, size=24, color="#4B0082"),
            bgcolor=ft.Colors.with_opacity(0.8, ft.Colors.WHITE),
            padding=ft.padding.symmetric(horizontal=10, vertical=2),
            border_radius=8
        )
        
        return ft.Container(
            content=ft.Row([menu, logo], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
            border=ft.border.only(bottom=ft.border.BorderSide(2, "#eeeeee")),
            padding=ft.padding.only(bottom=10, top=10),
            margin=ft.margin.only(bottom=20)
        )

    def build_screen(screen):
        # --- CRITICAL FIX 3: The foreground Column handles the scrolling now, sliding safely over the fixed background! ---
        content = ft.Column(expand=True, horizontal_alignment=ft.CrossAxisAlignment.CENTER, scroll="auto")
        
        if screen not in ["welcome", "login_form", "register_form", "after_register_step"]:
            content.controls.append(get_header())

        if screen == "welcome":
            content.controls.extend([
                ft.Container(
                    content=ft.Text("מערכת הפעילויות של אילת", size=24, color=ft.Colors.WHITE, weight=ft.FontWeight.BOLD),
                    bgcolor="#4B0082", padding=20, border_radius=15, alignment=ft.Alignment.CENTER, width=400
                ),
                ft.Divider(height=20, color=ft.Colors.TRANSPARENT),
                ft.Button(content=ft.Text("התחברות למערכת"), bgcolor=ft.Colors.BLUE_700, color=ft.Colors.WHITE, width=280, height=45, on_click=lambda _: render("login_form")),
                ft.Button(content=ft.Text("הרשמה (משתמש חדש)"), bgcolor=ft.Colors.AMBER_800, color=ft.Colors.WHITE, width=280, height=45, on_click=lambda _: render("register_form")),
                ft.Divider(height=20),
                ft.Button(content=ft.Text("כניסה כאורח"), bgcolor=ft.Colors.CYAN_700, color=ft.Colors.WHITE, width=280, height=45, on_click=lambda _: (backend.user_session.update({"name": "אורח"}), render("search_screen")))
            ])

        elif screen == "login_form":
            err_txt = ft.Text(color=ft.Colors.RED, bgcolor=ft.Colors.WHITE)
            id_box = ft.TextField(label="שם/אימייל:", width=350, rtl=True, bgcolor=ft.Colors.with_opacity(0.9, ft.Colors.WHITE))
            pass_box = ft.TextField(label="סיסמה:", password=True, can_reveal_password=True, width=350, rtl=True, bgcolor=ft.Colors.with_opacity(0.9, ft.Colors.WHITE))
            
            def handle_login(e):
                if not id_box.value or not pass_box.value: err_txt.value = "נא להזין שם משתמש/אימייל וסיסמה!"
                elif backend.login(id_box.value, pass_box.value): render("search_screen")
                else: err_txt.value = "פרטי ההתחברות שגויים!"
                page.update()

            content.controls.extend([
                ft.Container(content=ft.Text("התחברות", size=28, weight=ft.FontWeight.BOLD, color="#4B0082"), bgcolor=ft.Colors.with_opacity(0.8, ft.Colors.WHITE), padding=10, border_radius=8),
                id_box, pass_box, err_txt,
                ft.Row([
                    ft.Button(content=ft.Text("חזרה"), width=150, on_click=lambda _: render("welcome")),
                    ft.Button(content=ft.Text("כניסה"), width=150, bgcolor=ft.Colors.GREEN, color=ft.Colors.WHITE, on_click=handle_login)
                ], alignment=ft.MainAxisAlignment.CENTER)
            ])

        elif screen == "register_form":
            err_txt = ft.Text(color=ft.Colors.RED, bgcolor=ft.Colors.WHITE)
            name_box = ft.TextField(label="שם משתמש:", width=350, rtl=True, bgcolor=ft.Colors.with_opacity(0.9, ft.Colors.WHITE))
            email_box = ft.TextField(label="אימייל:", width=350, rtl=True, bgcolor=ft.Colors.with_opacity(0.9, ft.Colors.WHITE))
            pass_box = ft.TextField(label="סיסמה:", password=True, can_reveal_password=True, width=350, rtl=True, bgcolor=ft.Colors.with_opacity(0.9, ft.Colors.WHITE))
            pass_conf = ft.TextField(label="אימות סיסמה:", password=True, can_reveal_password=True, width=350, rtl=True, bgcolor=ft.Colors.with_opacity(0.9, ft.Colors.WHITE))

            def handle_register(e):
                if not name_box.value or not email_box.value or not pass_box.value: err_txt.value = "יש למלא את כל השדות!"
                elif pass_box.value != pass_conf.value: err_txt.value = "הסיסמאות אינן תואמות!"
                elif "@" not in email_box.value: err_txt.value = "נא להזין כתובת אימייל תקינה!"
                elif backend.register(name_box.value, email_box.value, pass_box.value): render("after_register_step")
                else: err_txt.value = "שם המשתמש או האימייל כבר קיימים במערכת."
                page.update()

            content.controls.extend([
                ft.Container(content=ft.Text("הרשמה למערכת", size=28, weight=ft.FontWeight.BOLD, color="#f57c00"), bgcolor=ft.Colors.with_opacity(0.8, ft.Colors.WHITE), padding=10, border_radius=8),
                name_box, email_box, pass_box, pass_conf, err_txt,
                ft.Row([
                    ft.Button(content=ft.Text("חזרה"), width=150, on_click=lambda _: render("welcome")),
                    ft.Button(content=ft.Text("צור משתמש"), width=150, bgcolor=ft.Colors.AMBER_800, color=ft.Colors.WHITE, on_click=handle_register)
                ], alignment=ft.MainAxisAlignment.CENTER)
            ])

        elif screen == "after_register_step":
            new_user = backend.last_registered_user
            content.controls.extend([
                ft.Container(content=ft.Text("מערכת הפעילויות של אילת", size=24, color=ft.Colors.WHITE), bgcolor="#4B0082", padding=20, border_radius=15),
                ft.Container(
                    content=ft.Column([
                        ft.Text(f"היי {new_user}!", size=32, color=ft.Colors.BLUE_800, weight=ft.FontWeight.BOLD),
                        ft.Text("נרשמת בהצלחה למערכת.", size=18)
                    ], horizontal_alignment=ft.CrossAxisAlignment.CENTER),
                    bgcolor=ft.Colors.BLUE_50, padding=40, border_radius=15, margin=ft.margin.only(top=20)
                ),
                ft.Button(content=ft.Text("להתחבר עכשיו"), width=300, height=55, bgcolor=ft.Colors.BLUE_600, color=ft.Colors.WHITE, on_click=lambda _: render("login_form"))
            ])

        elif screen == "personal_area":
            username = backend.user_session["name"]
            if username == "אורח" or not username:
                content.controls.extend([
                    ft.Container(content=ft.Text("משתמשים אורחים לא יכולים לשמור נתונים. נא להתחבר למערכת.", color=ft.Colors.RED, size=18), bgcolor=ft.Colors.WHITE, padding=10, border_radius=8),
                    ft.Button(content=ft.Text("חזרה לחיפוש"), on_click=lambda _: render("search_screen"), bgcolor=ft.Colors.WHITE)
                ])
                return content

            user_data = backend.users_db[username]
            avatar_url = user_data.get("avatar", "")

            if avatar_url:
                avatar_display = ft.Container(
                    content=ft.Image(src=avatar_url, fit="cover"),
                    width=120, height=120, border_radius=60, border=ft.border.all(3, "#4B0082"), clip_behavior=ft.ClipBehavior.HARD_EDGE
                )
            else:
                avatar_display = ft.CircleAvatar(content=ft.Text(username[0].upper(), size=40, color=ft.Colors.WHITE), radius=60, bgcolor=ft.Colors.GREY)

            url_input = ft.TextField(value=avatar_url, label="הדבק קישור (URL)...", width=200, rtl=True, bgcolor=ft.Colors.WHITE)
            btn_save_link = ft.Button(content=ft.Text("שמור קישור"), bgcolor=ft.Colors.BLUE_600, color=ft.Colors.WHITE, on_click=lambda e: (backend.update_avatar(url_input.value), render("personal_area")))
            
            upload_btn = ft.Button(content=ft.Text("העלה מהמחשב"), icon=ft.Icons.UPLOAD_FILE, on_click=lambda e: page.run_task(on_avatar_upload), bgcolor=ft.Colors.WHITE)
            
            avatar_input_row = ft.Row([upload_btn, btn_save_link, url_input, ft.Text("קישור תמונה:")], alignment=ft.MainAxisAlignment.CENTER, wrap=True)

            avatar_section = ft.Container(
                content=ft.Column([
                    ft.Text("תמונת פרופיל", size=18, weight=ft.FontWeight.BOLD),
                    avatar_display,
                    avatar_input_row
                ], horizontal_alignment=ft.CrossAxisAlignment.CENTER),
                border=ft.border.all(1, "#eeeeee"), padding=20, border_radius=10, bgcolor=ft.Colors.with_opacity(0.95, ft.Colors.WHITE)
            )

            inv_people = {v: k for k, v in backend.people_map.items()}
            inv_budget = {v: k for k, v in backend.budget_options.items()}
            prefs = user_data.get("preferences", {})
            
            pref_area = ft.Dropdown(options=[ft.dropdown.Option(key=a, text=a) for a in backend.areas], value=prefs.get("area", "אילת"), label="אזור מועדף", width=200, bgcolor=ft.Colors.WHITE)
            pref_budget = ft.Dropdown(options=[ft.dropdown.Option(key=k, text=k) for k in backend.budget_options.keys()], value=inv_budget.get(prefs.get("budget", 1000), 'ללא הגבלה'), label="תקציב מקסימלי", width=200, bgcolor=ft.Colors.WHITE)
            pref_people = ft.Dropdown(options=[ft.dropdown.Option(key=k, text=k) for k in backend.people_map.keys()], value=inv_people.get(prefs.get("people_count", 4), '3-5'), label="כמות אנשים", width=200, bgcolor=ft.Colors.WHITE)

            btn_save_prefs = ft.Button(content=ft.Text("שמור העדפות"), bgcolor=ft.Colors.GREEN, color=ft.Colors.WHITE)
            def save_defaults(e):
                backend.update_preferences(backend.budget_options[pref_budget.value], pref_area.value, backend.people_map[pref_people.value])
                btn_save_prefs.content = ft.Text("נשמר בהצלחה!")
                page.update()
            btn_save_prefs.on_click = save_defaults

            prefs_section = ft.Container(
                content=ft.Column([
                    ft.Text("הגדרות חיפוש קבועות", size=18, weight=ft.FontWeight.BOLD),
                    ft.Row([pref_area, pref_budget, pref_people], wrap=True, alignment=ft.MainAxisAlignment.CENTER),
                    btn_save_prefs
                ], horizontal_alignment=ft.CrossAxisAlignment.CENTER),
                border=ft.border.all(1, "#eeeeee"), padding=20, border_radius=10, bgcolor=ft.Colors.with_opacity(0.95, ft.Colors.WHITE)
            )

            fav_col = ft.Column()
            favorites = user_data.get("favorites", [])
            if not favorites:
                fav_col.controls.append(ft.Text("עדיין אין לך פעילויות במועדפים."))
            else:
                for act in backend.activities_db.values():
                    if act['name'] in favorites:
                        fav_col.controls.append(ft.Text(f"❤️ {act['name']} - {act['price']} ₪", size=16, color="#4B0082"))

            favs_section = ft.Container(
                content=ft.Column([ft.Text("המועדפים שלי", size=18, weight=ft.FontWeight.BOLD), fav_col]),
                border=ft.border.all(1, "#eeeeee"), padding=20, border_radius=10, bgcolor=ft.Colors.with_opacity(0.95, ft.Colors.WHITE), width=page.width
            )

            content.controls.extend([
                ft.Container(content=ft.Text(f"אזור אישי - {username}", size=24, color="#4B0082"), bgcolor=ft.Colors.with_opacity(0.8, ft.Colors.WHITE), padding=5, border_radius=8),
                avatar_section, prefs_section, favs_section,
                ft.Button(content=ft.Text("חזרה לחיפוש"), on_click=lambda _: render("search_screen"), bgcolor=ft.Colors.WHITE)
            ])

        elif screen == "search_screen":
            inv_people = {v: k for k, v in backend.people_map.items()}
            inv_budget = {v: k for k, v in backend.budget_options.items()}
            
            def exec_search(e=None):
                backend.user_session.update({
                    "budget": backend.budget_options[budget_dd.value],
                    "area": area_dd.value,
                    "people_count": backend.people_map[people_dd.value],
                    "sort_by": "default"
                })
                render("results")

            people_dd = ft.Dropdown(
                options=[ft.dropdown.Option(key=k, text=k) for k in backend.people_map.keys()],
                value=inv_people.get(backend.user_session['people_count'], '3-5'),
                width=300,
                on_select=exec_search,
                bgcolor=ft.Colors.WHITE
            )
            budget_dd = ft.Dropdown(
                options=[ft.dropdown.Option(key=k, text=k) for k in backend.budget_options.keys()],
                value=inv_budget.get(backend.user_session['budget'], 'ללא הגבלה'),
                width=300,
                on_select=exec_search,
                bgcolor=ft.Colors.WHITE
            )
            area_dd = ft.Dropdown(
                options=[ft.dropdown.Option(key=a, text=a) for a in backend.areas],
                value=backend.user_session['area'],
                width=300,
                on_select=exec_search,
                bgcolor=ft.Colors.WHITE
            )

            form_box = ft.Container(
                content=ft.Column([
                    ft.Text("חיפוש פעילויות", size=24, color="#4B0082", weight=ft.FontWeight.BOLD),
                    ft.Text("כמה אנשים אתם?"), people_dd,
                    ft.Text("תקציב מקסימלי:"), budget_dd,
                    ft.Text("איזור:"), area_dd,
                    ft.Button(content=ft.Text("🔍 צפה בתוצאות"), bgcolor=ft.Colors.AMBER_800, color=ft.Colors.WHITE, height=50, width=300, on_click=exec_search)
                ], horizontal_alignment=ft.CrossAxisAlignment.CENTER),
                bgcolor=ft.Colors.with_opacity(0.95, ft.Colors.WHITE), padding=30, border_radius=16,
                shadow=ft.BoxShadow(spread_radius=1, blur_radius=15, color=ft.Colors.BLACK_12)
            )
            content.controls.append(form_box)

        elif screen == "results":
            results_count_text = ft.Container(
                content=ft.Text("מחפש פעילויות...", size=20, color=ft.Colors.RED_700, weight=ft.FontWeight.BOLD),
                bgcolor=ft.Colors.with_opacity(0.8, ft.Colors.WHITE),
                padding=ft.padding.symmetric(horizontal=10, vertical=5),
                border_radius=8
            )
            content.controls.append(results_count_text)

            inv_people = {v: k for k, v in backend.people_map.items()}
            inv_budget = {v: k for k, v in backend.budget_options.items()}

            sort_dd = ft.Dropdown(
                options=[
                    ft.dropdown.Option(key='default', text='ברירת מחדל'),
                    ft.dropdown.Option(key='price_asc', text='מחיר: נמוך לגבוה'),
                    ft.dropdown.Option(key='price_desc', text='מחיר: גבוה לנמוך')
                ],
                value=backend.user_session['sort_by'], label="מיון", width=150, bgcolor=ft.Colors.WHITE
            )

            people_dd = ft.Dropdown(
                options=[ft.dropdown.Option(key=k, text=k) for k in backend.people_map.keys()],
                value=inv_people.get(backend.user_session['people_count'], '3-5'), label="אנשים", width=120, bgcolor=ft.Colors.WHITE
            )

            budget_dd = ft.Dropdown(
                options=[ft.dropdown.Option(key=k, text=k) for k in backend.budget_options.keys()],
                value=inv_budget.get(backend.user_session['budget'], 'ללא הגבלה'), label="תקציב", width=150, bgcolor=ft.Colors.WHITE
            )

            area_dd = ft.Dropdown(
                options=[ft.dropdown.Option(key=a, text=a) for a in backend.areas],
                value=backend.user_session['area'], label="איזור", width=120, bgcolor=ft.Colors.WHITE
            )

            filter_row = ft.Container(
                content=ft.Row([sort_dd, people_dd, budget_dd, area_dd], wrap=True, alignment=ft.MainAxisAlignment.CENTER),
                bgcolor=ft.Colors.with_opacity(0.9, ft.Colors.BLUE_50), padding=15, border_radius=8, margin=ft.margin.only(bottom=20)
            )
            content.controls.append(filter_row)

            # This inner column holds the cards, keeping the search filters fixed at the top if needed!
            list_container = ft.Column(expand=True)
            content.controls.append(list_container)

            def update_results(e=None):
                backend.user_session.update({
                    "sort_by": sort_dd.value,
                    "people_count": backend.people_map[people_dd.value],
                    "budget": backend.budget_options[budget_dd.value],
                    "area": area_dd.value
                })

                matches = backend.filter_data()
                username = backend.user_session["name"]
                user_favorites = backend.users_db[username].get("favorites", []) if username and username != "אורח" else []

                list_container.controls.clear()

                if not matches:
                    results_count_text.content.value = "לא נמצאו פעילויות מתאימות להגדרות אלו..."
                else:
                    results_count_text.content.value = f"מצאנו {len(matches)} פעילויות עבורך:"
                    for item in matches:
                        is_fav = item['name'] in user_favorites

                        def make_go_to_details(selected_item):
                            def go_to_details(e):
                                backend.current_event = selected_item
                                render("event_details")
                            return go_to_details

                        def make_open_map(selected_item):
                            async def open_map(e):
                                full_address = f"{selected_item['address']}, {selected_item['location']}"
                                encoded_address = urllib.parse.quote(full_address)
                                if page.platform in [ft.PagePlatform.IOS, ft.PagePlatform.MACOS]:
                                    url = f"http://maps.apple.com/?q={encoded_address}"
                                else:
                                    url = f"https://www.google.com/maps/search/?api=1&query={encoded_address}"
                                await page.launch_url(url)
                            return open_map

                        title_btn = ft.Button(
                            content=ft.Text(item['name'], size=20, weight=ft.FontWeight.W_900, color="#2c3e50", max_lines=2, overflow=ft.TextOverflow.ELLIPSIS),
                            on_click=make_go_to_details(item),
                            bgcolor=ft.Colors.TRANSPARENT,
                            style=ft.ButtonStyle(padding=0)
                        )

                        fav_btn = ft.IconButton(
                            icon=ft.Icons.FAVORITE if is_fav else ft.Icons.FAVORITE_BORDER,
                            icon_color=ft.Colors.RED if is_fav else ft.Colors.GREY,
                            data=item['name']
                        )

                        def on_fav_click(e):
                            if username == "אורח" or not username:
                                e.control.icon = ft.Icons.LOCK
                                page.update()
                                return
                            act_name = e.control.data
                            backend.toggle_favorite(act_name)
                            is_now_fav = act_name in backend.users_db[username].get("favorites", [])
                            e.control.icon = ft.Icons.FAVORITE if is_now_fav else ft.Icons.FAVORITE_BORDER
                            e.control.icon_color = ft.Colors.RED if is_now_fav else ft.Colors.GREY
                            page.update()

                        fav_btn.on_click = on_fav_click

                        price_tag = ft.Container(
                            content=ft.Text(f"{item['price']} ₪", color="#2e7d32", size=16, weight=ft.FontWeight.BOLD),
                            bgcolor="#99e89f", padding=ft.padding.symmetric(horizontal=12, vertical=4),
                            border_radius=20, border=ft.border.all(1, "#c8e6c9")
                        )

                        img_box = ft.Container(
                            content=ft.Image(src=item['image_url'], fit="cover"),
                            width=140, height=120, border_radius=8,
                            border=ft.border.all(2, item.get('color', '#333')),
                            clip_behavior=ft.ClipBehavior.HARD_EDGE
                        )

                        top_row = ft.Row([
                            ft.Container(content=title_btn, expand=True, padding=ft.padding.only(left=10)),
                            price_tag
                        ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN, vertical_alignment=ft.CrossAxisAlignment.START)

                        address_btn = ft.Container(
                            content=ft.Text(f"📍 {item['address']}", color=ft.Colors.RED_700, size=14, weight=ft.FontWeight.BOLD),
                            on_click=make_open_map(item),
                            ink=True,
                            border_radius=5,
                            padding=ft.padding.only(top=2, bottom=2)
                        )

                        details_col = ft.Column([
                            top_row,
                            address_btn,
                            ft.Text(item['desc'], size=14, max_lines=2, overflow=ft.TextOverflow.ELLIPSIS),
                            fav_btn
                        ], expand=True, margin=ft.margin.only(right=25))

                        card_row = ft.Row([img_box, details_col], alignment=ft.MainAxisAlignment.START, vertical_alignment=ft.CrossAxisAlignment.START)

                        card_container = ft.Container(
                            content=card_row,
                            border=ft.border.all(1, "#dddddd"), border_radius=12, padding=15, margin=ft.margin.only(bottom=15),
                            bgcolor=ft.Colors.with_opacity(0.95, ft.Colors.WHITE), shadow=ft.BoxShadow(spread_radius=1, blur_radius=8, color=ft.Colors.BLACK_12)
                        )
                        list_container.controls.append(card_container)
                
                if e:
                    page.update()

            sort_dd.on_select = update_results
            people_dd.on_select = update_results
            budget_dd.on_select = update_results
            area_dd.on_select = update_results

            update_results()

            content.controls.append(ft.Button(content=ft.Text("➔ חזור לחיפוש"), on_click=lambda _: render("search_screen"), bgcolor=ft.Colors.WHITE))

        elif screen == "event_details":
            item = backend.current_event
            if not item: return

            username = backend.user_session["name"]
            user_favorites = backend.users_db[username].get("favorites", []) if username and username != "אורח" else []
            is_fav = item['name'] in user_favorites

            fav_btn = ft.IconButton(
                icon=ft.Icons.FAVORITE if is_fav else ft.Icons.FAVORITE_BORDER,
                icon_color=ft.Colors.RED if is_fav else ft.Colors.GREY,
                icon_size=30
            )

            def on_fav_click(e):
                if username == "אורח": e.control.icon = ft.Icons.LOCK; page.update(); return
                backend.toggle_favorite(item['name'])
                is_now_fav = item['name'] in backend.users_db[username].get("favorites", [])
                e.control.icon = ft.Icons.FAVORITE if is_now_fav else ft.Icons.FAVORITE_BORDER
                e.control.icon_color = ft.Colors.RED if is_now_fav else ft.Colors.GREY
                page.update()
            
            fav_btn.on_click = on_fav_click

            msg_out = ft.Text(color=ft.Colors.GREEN_700, bgcolor=ft.Colors.WHITE)
            def handle_book(e):
                msg_out.value = "הפיצ'ר הזה יגיע בקרוב! 🚀"
                page.update()

            async def open_map(e):
                full_address = f"{item['address']}, {item['location']}"
                encoded_address = urllib.parse.quote(full_address)
                
                if page.platform in [ft.PagePlatform.IOS, ft.PagePlatform.MACOS]:
                    url = f"http://maps.apple.com/?q={encoded_address}"
                else:
                    url = f"https://www.google.com/maps/search/?api=1&query={encoded_address}"
                    
                await page.launch_url(url)

            map_button = ft.Container(
                content=ft.Row([
                    ft.Text(f"📍 נווט אל: {item['address']}", color=ft.Colors.RED_700, weight=ft.FontWeight.BOLD)
                ], tight=True),
                bgcolor=ft.Colors.RED_50, padding=10, border_radius=20, alignment=ft.Alignment.CENTER_RIGHT,
                on_click=open_map,
                ink=True 
            )

            content.controls.extend([
                ft.Container(
                    content=ft.Image(src=item['image_url'], fit="cover"),
                    width=page.width, height=250, border_radius=15,
                    shadow=ft.BoxShadow(blur_radius=16, color=ft.Colors.BLACK_26),
                    clip_behavior=ft.ClipBehavior.HARD_EDGE
                ),
                ft.Row([
                    ft.Container(content=ft.Text(item['name'], size=26, weight=ft.FontWeight.W_800, color="#4B0082"), expand=True, bgcolor=ft.Colors.with_opacity(0.8, ft.Colors.WHITE), padding=5, border_radius=8),
                    ft.Container(content=ft.Text(f"{item['price']} ₪ לאדם", color="#2e7d32", size=16, weight=ft.FontWeight.BOLD), bgcolor="#99e89f", padding=ft.padding.symmetric(horizontal=15, vertical=5), border_radius=20)
                ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN, margin=ft.margin.only(top=15), vertical_alignment=ft.CrossAxisAlignment.START),
                
                map_button,
                
                ft.Container(
                    content=ft.Column([
                        ft.Text("על הפעילות:", size=18, weight=ft.FontWeight.BOLD),
                        ft.Text(item['desc'], size=16, color=ft.Colors.GREY_800)
                    ]),
                    bgcolor=ft.Colors.with_opacity(0.95, ft.Colors.WHITE), border=ft.border.all(1, "#eeeeee"), padding=20, border_radius=12, margin=ft.margin.only(top=15, bottom=15), width=page.width
                ),

                ft.Container(
                    content=ft.Column([
                        ft.Row([
                            ft.Button(content=ft.Text("📅 צור אירוע / הזמן מקום"), bgcolor=ft.Colors.GREEN, color=ft.Colors.WHITE, height=50, expand=True, on_click=handle_book),
                            fav_btn
                        ]),
                        msg_out
                    ], horizontal_alignment=ft.CrossAxisAlignment.CENTER),
                    bgcolor=ft.Colors.with_opacity(0.9, ft.Colors.BLUE_50), padding=20, border_radius=15, width=page.width
                ),
                
                ft.Button(content=ft.Text("➔ חזרה לתוצאות"), on_click=lambda _: render("results"), margin=ft.margin.only(top=20), bgcolor=ft.Colors.WHITE)
            ])

        return content

    # --- CRITICAL FIX 4: Add the layout straight to the page (Do NOT wrap the Stack in SafeArea) ---
    page.add(main_layout)
    render("welcome")

ft.app(target=main, assets_dir="assets")
