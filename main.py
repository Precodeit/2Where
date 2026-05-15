import flet as ft
import json
import os
import base64
import warnings
import urllib.parse
from supabase import create_client, Client

# העלמת אזהרות ה-Deprecation
warnings.filterwarnings("ignore", category=DeprecationWarning)

class AppBackend:
    def __init__(self):
        # --- SUPABASE KEYS GO HERE ---
        self.url = "https://nkflxdjkfaqnssatmmtf.supabase.co"
        self.key = "sb_publishable_dcPy9FjqCy0u0DGBPkSSUQ_z7Ap45cv"
        # -----------------------------
        
        try:
            self.supabase: Client = create_client(self.url, self.key)
        except Exception as e:
            print(f"Supabase Init Error: {e}")

        self.activities_file = 'activities.json'
        self.activities_db = self.load_activities()
        
        self.history = []
        self.current_screen = None
        self.current_event = None

        self.user_session = {"name": "", "id": None, "budget": 1000, "area": "אילת", "people_count": 4, "sort_by": "default", "avatar_url": ""}
        
        # --- THE SPEED FIX: Local Cache Dictionary ---
        self.local_cache = {}
        
        self.people_map = {'1-2': 2, '3-5': 4, '5-7': 6, '10+': 12}
        self.budget_options = {'חינם': 0, ' עד 50 ש"ח': 50, 'עד 100 ש"ח': 100, 'ללא הגבלה': 1000}
        self.areas = ['אילת', 'דרום', 'מרכז', 'צפון']

    def load_activities(self):
        if os.path.exists(self.activities_file):
            with open(self.activities_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        return {}

    # --- Authentication (Supabase) ---
    def register(self, username, email, password):
        try:
            auth_res = self.supabase.auth.sign_up({"email": email, "password": password})
            if not auth_res.user: return False
            
            user_id = auth_res.user.id
            self.supabase.table("profiles").insert({
                "id": user_id,
                "username": username,
                "email": email,
                "avatar_url": "",
                "preferences": {"budget": 1000, "area": "אילת", "people_count": 4}
            }).execute()
            
            self.last_registered_user = username
            return True
        except Exception as e:
            print(f"Registration Error: {e}")
            return False

    def login(self, identifier, password):
        try:
            # 1. Determine if the identifier is an email or a username
            target_email = identifier
            
            if "@" not in identifier:
                # If there's no "@", we assume it's a username and look up the email
                profile_check = self.supabase.table("profiles").select("email").eq("username", identifier).execute()
                
                if profile_check.data and len(profile_check.data) > 0:
                    target_email = profile_check.data[0]["email"]
                else:
                    # No username found
                    return False

            # 2. Authenticate with the email (whether original or looked up)
            res = self.supabase.auth.sign_in_with_password({"email": target_email, "password": password})
            user_id = res.user.id
            
            # 3. Load the full profile and cache it for speed
            profile = self.supabase.table("profiles").select("*").eq("id", user_id).single().execute()
            
            self.user_session.update({
                "name": profile.data["username"],
                "id": user_id,
                "avatar_url": profile.data.get("avatar_url", "")
            })
            
            if profile.data.get("preferences"):
                self.user_session.update(profile.data["preferences"])
                
            self.local_cache = {} # Reset cache for the new user
            return True
            
        except Exception as e:
            print(f"Login Error: {e}")
            return False

    def update_avatar(self, url):
        if self.user_session["id"]:
            self.supabase.table("profiles").update({"avatar_url": url}).eq("id", self.user_session["id"]).execute()
            self.user_session["avatar_url"] = url

    def update_preferences(self, budget, area, people_count):
        if self.user_session["id"]:
            prefs = {"budget": budget, "area": area, "people_count": people_count}
            self.supabase.table("profiles").update({"preferences": prefs}).eq("id", self.user_session["id"]).execute()
            self.user_session.update(prefs)

    # --- Favorites (Supabase + Cache) ---
    def toggle_favorite(self, activity_name):
        if not self.user_session["id"]: return
        favs = self.get_user_favorites()
        
        if activity_name in favs:
            favs.remove(activity_name)
            self.supabase.table("favorites").delete().eq("user_id", self.user_session["id"]).eq("activity_name", activity_name).execute()
        else:
            favs.append(activity_name)
            self.supabase.table("favorites").insert({"user_id": self.user_session["id"], "activity_name": activity_name}).execute()
            
        self.local_cache["favorites"] = favs

    def get_user_favorites(self):
        if not self.user_session["id"]: return []
        if "favorites" in self.local_cache:
            return self.local_cache["favorites"]
            
        res = self.supabase.table("favorites").select("activity_name").eq("user_id", self.user_session["id"]).execute()
        favs = [item['activity_name'] for item in res.data]
        self.local_cache["favorites"] = favs
        return favs

    # --- Friends (Supabase + Cache) ---
    def send_friend_request(self, target_username):
        current_user = self.user_session["name"]
        if current_user == "אורח" or not current_user:
            return False, "יש להתחבר כדי לשלוח בקשות חברות."
        if target_username == current_user:
            return False, "אי אפשר לשלוח בקשה לעצמך."
        
        try:
            target = self.supabase.table("profiles").select("id").eq("username", target_username).single().execute()
            if not target.data: return False, "משתמש לא נמצא במערכת."
            
            existing = self.supabase.table("friendship").select("*").eq("user_id", self.user_session["id"]).eq("friend_id", target.data["id"]).execute()
            reverse = self.supabase.table("friendship").select("*").eq("user_id", target.data["id"]).eq("friend_id", self.user_session["id"]).execute()
            
            if existing.data or reverse.data:
                return False, "כבר קיימת בקשה או חברות עם משתמש זה."
                
            self.supabase.table("friendship").insert({
                "user_id": self.user_session["id"],
                "friend_id": target.data["id"],
                "status": "pending"
            }).execute()
            
            self.local_cache.pop("friends", None)
            return True, "בקשת החברות נשלחה בהצלחה!"
        except Exception as e:
            return False, "שגיאה בשליחת הבקשה."

    def handle_friend_request(self, target_username, accept=True):
        target = self.supabase.table("profiles").select("id").eq("username", target_username).single().execute()
        if accept:
            self.supabase.table("friendship").update({"status": "accepted"}).eq("user_id", target.data["id"]).eq("friend_id", self.user_session["id"]).execute()
        else:
            self.supabase.table("friendship").delete().eq("user_id", target.data["id"]).eq("friend_id", self.user_session["id"]).execute()
        self.local_cache.pop("friends", None)

    def remove_friend(self, target_username):
        target = self.supabase.table("profiles").select("id").eq("username", target_username).single().execute()
        self.supabase.table("friendship").delete().eq("user_id", self.user_session["id"]).eq("friend_id", target.data["id"]).execute()
        self.supabase.table("friendship").delete().eq("user_id", target.data["id"]).eq("friend_id", self.user_session["id"]).execute()
        self.local_cache.pop("friends", None)

    def get_friends_data(self):
        if not self.user_session["id"]: return [], []
        if "friends" in self.local_cache:
            return self.local_cache["friends"]
        
        reqs = self.supabase.table("friendship").select("profiles!user_id(username)").eq("friend_id", self.user_session["id"]).eq("status", "pending").execute()
        pending = [item['profiles']['username'] for item in reqs.data if item['profiles']]
        
        f1 = self.supabase.table("friendship").select("profiles!friend_id(username, avatar_url)").eq("user_id", self.user_session["id"]).eq("status", "accepted").execute()
        f2 = self.supabase.table("friendship").select("profiles!user_id(username, avatar_url)").eq("friend_id", self.user_session["id"]).eq("status", "accepted").execute()
        
        friends = []
        for item in f1.data:
            if item['profiles']: friends.append({"name": item['profiles']['username'], "avatar": item['profiles']['avatar_url']})
        for item in f2.data:
            if item['profiles']: friends.append({"name": item['profiles']['username'], "avatar": item['profiles']['avatar_url']})
            
        self.local_cache["friends"] = (pending, friends)
        return pending, friends

    # --- Events (Supabase + Cache) ---
    def create_event(self, activity_name, date_time, note, invited_usernames):
        event_res = self.supabase.table("events").insert({
            "host_id": self.user_session["id"],
            "activity_name": activity_name,
            "date_time": date_time,
            "note": note
        }).execute()
        
        event_id = event_res.data[0]['id']
        
        for name in invited_usernames:
            friend = self.supabase.table("profiles").select("id").eq("username", name).single().execute()
            if friend.data:
                self.supabase.table("event_invitations").insert({
                    "event_id": event_id,
                    "invitee_id": friend.data["id"]
                }).execute()
        self.local_cache.pop("events", None)

    def get_my_events_and_invites(self):
        if not self.user_session["id"]: return [], []
        if "events" in self.local_cache:
            return self.local_cache["events"]
        
        evs = self.supabase.table("events").select("*").eq("host_id", self.user_session["id"]).execute()
        inv_res = self.supabase.table("event_invitations").select("event_id").eq("invitee_id", self.user_session["id"]).execute()
        
        formatted_invites = []
        for inv in inv_res.data:
            ev_data = self.supabase.table("events").select("activity_name, date_time, note, profiles!host_id(username)").eq("id", inv["event_id"]).single().execute()
            if ev_data.data:
                formatted_invites.append({
                    "activity": ev_data.data['activity_name'],
                    "host": ev_data.data['profiles']['username'] if ev_data.data['profiles'] else "לא ידוע",
                    "date_time": ev_data.data['date_time'],
                    "note": ev_data.data['note']
                })
                
        hosted_events = []
        for ev in evs.data:
            invites = self.supabase.table("event_invitations").select("profiles!invitee_id(username)").eq("event_id", ev["id"]).execute()
            invited_list = [i['profiles']['username'] for i in invites.data if i['profiles']]
            hosted_events.append({
                "activity": ev["activity_name"],
                "date_time": ev["date_time"],
                "invited": invited_list
            })
            
        self.local_cache["events"] = (hosted_events, formatted_invites)
        return hosted_events, formatted_invites

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
    page.title = "2Where"
    page.rtl = True
    page.theme_mode = ft.ThemeMode.LIGHT
    page.fonts = {"Rubik": "https://fonts.googleapis.com/css2?family=Rubik:wght@400;600;800&display=swap"}
    page.theme = ft.Theme(font_family="Rubik")
    page.horizontal_alignment = ft.CrossAxisAlignment.CENTER
    page.window.width = 450
    page.window.height = 800
    page.padding = 0
    page.spacing = 0

    backend = AppBackend()

    content_container = ft.Container(expand=True, padding=10)

    # --- Custom Dialog Overlay ---
    dialog_overlay = ft.Container(
        visible=False,
        bgcolor=ft.Colors.with_opacity(0.6, ft.Colors.BLACK),
        left=0, right=0, top=0, bottom=0,
        alignment=ft.Alignment(0, 0)
    )

    def show_popup(content_widget):
        dialog_overlay.content = content_widget
        dialog_overlay.visible = True
        page.update()

    def hide_popup(e=None):
        dialog_overlay.visible = False
        page.update()
    # --------------------------------

    main_layout = ft.Stack(
        controls=[
            ft.Image(src="bg.jpg", fit="cover", left=0, right=0, top=0, bottom=0),
            ft.SafeArea(content=content_container, left=0, right=0, top=0, bottom=0),
            dialog_overlay
        ],
        expand=True
    )

    def on_avatar_upload_result(e):
        try:
            if e.files and len(e.files) > 0:
                f = e.files[0]
                if f.path:
                    with open(f.path, "rb") as image_file:
                        file_bytes = image_file.read()
                    
                    mime_type = "image/jpeg"
                    if f.name.lower().endswith(".png"):
                        mime_type = "image/png"
                    
                    encoded_string = base64.b64encode(file_bytes).decode('utf-8')
                    data_url = f"data:{mime_type};base64,{encoded_string}"
                    backend.update_avatar(data_url)
                    render("personal_area")
        except Exception as ex:
            print(f"Error picking file: {ex}")

    file_picker = ft.FilePicker()
    file_picker.on_result = on_avatar_upload_result

    def render(screen_name, is_back=False):
        if not is_back and backend.current_screen and backend.current_screen != screen_name:
            backend.history.append(backend.current_screen)
            
        backend.current_screen = screen_name
        content_container.content = build_screen(screen_name)
        page.update()

    def go_back(e=None):
        if backend.history:
            previous_screen = backend.history.pop()
            render(previous_screen, is_back=True)
        else:
            render("welcome", is_back=True)

    def get_header():
        user_name = backend.user_session.get("name", "אורח")
        
        # Fast avatar load
        avatar_url = backend.user_session.get("avatar_url", "")

        if avatar_url:
            avatar = ft.CircleAvatar(foreground_image_url=avatar_url, radius=22)
        else:
            first_letter = user_name[0].upper() if user_name else "U"
            avatar = ft.CircleAvatar(content=ft.Text(first_letter, color=ft.Colors.WHITE), bgcolor="#4B0082", radius=22)

        def handle_menu(e):
            action = e.control.data
            if action == "logout":
                backend.user_session = {"name": "", "id": None, "budget": 1000, "area": "אילת", "people_count": 4, "sort_by": "default", "avatar_url": ""}
                backend.local_cache = {}
                backend.history.clear()
                render("welcome")
            elif action == "personal_area":
                render("personal_area")
            elif action == "search_screen":
                render("search_screen")
            elif action == "friends":
                render("friends")

        menu = ft.PopupMenuButton(
            content=avatar,
            items=[
                ft.PopupMenuItem(content=ft.Text("חיפוש פעילויות"), data="search_screen", on_click=handle_menu),
                ft.PopupMenuItem(content=ft.Text("אזור אישי"), data="personal_area", on_click=handle_menu),
                ft.PopupMenuItem(content=ft.Text("החברים שלי"), data="friends", on_click=handle_menu),
                ft.PopupMenuItem(content=ft.Text("התנתקות"), data="logout", on_click=handle_menu),
            ]
        )

        logo = ft.Container(
            content=ft.Text("2Where", weight=ft.FontWeight.W_800, size=24, color="#4B0082"),
            padding=0
        )
        
        return ft.Container(
            content=ft.Row([menu, logo], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
            padding=5,
            margin=5
        )

    def build_screen(screen):
        content = ft.Column(expand=True, horizontal_alignment=ft.CrossAxisAlignment.CENTER, scroll="auto")
        
        if screen not in ["welcome", "login_form", "register_form", "after_register_step"]:
            content.controls.append(get_header())

        if screen == "welcome":
            content.controls.extend([
                ft.Container(
                    content=ft.Text("ברוכים הבאים ל-2Where", size=24, color=ft.Colors.WHITE, weight=ft.FontWeight.BOLD),
                    bgcolor="#4B0082", padding=20, border_radius=15, alignment=ft.Alignment(0, 0), width=400
                ),
                ft.Divider(height=20, color=ft.Colors.TRANSPARENT),
                ft.Button(content=ft.Text("התחברות למערכת"), bgcolor=ft.Colors.BLUE_700, color=ft.Colors.WHITE, width=280, height=45, on_click=lambda _: render("login_form")),
                ft.Button(content=ft.Text("הרשמה (משתמש חדש)"), bgcolor=ft.Colors.AMBER_800, color=ft.Colors.WHITE, width=280, height=45, on_click=lambda _: render("register_form")),
                ft.Divider(height=20),
                ft.Button(content=ft.Text("כניסה כאורח"), bgcolor=ft.Colors.CYAN_700, color=ft.Colors.WHITE, width=280, height=45, on_click=lambda _: (backend.user_session.update({"name": "אורח"}), render("search_screen")))
            ])

        elif screen == "login_form":
            err_txt = ft.Text(color=ft.Colors.RED, bgcolor=ft.Colors.TRANSPARENT)
            id_box = ft.TextField(label="שם משתמש או אימייל", width=350, rtl=True, bgcolor=ft.Colors.with_opacity(0.9, ft.Colors.WHITE))
            pass_box = ft.TextField(label="סיסמה:", password=True, can_reveal_password=True, width=350, rtl=True, bgcolor=ft.Colors.with_opacity(0.9, ft.Colors.WHITE))
            
            def handle_login(e):
                if not id_box.value or not pass_box.value: err_txt.value = "נא להזין אימייל וסיסמה!"
                elif backend.login(id_box.value, pass_box.value): render("search_screen")
                else: err_txt.value = "פרטי ההתחברות שגויים!"
                page.update()

            content.controls.extend([
                ft.Container(content=ft.Text("התחברות", size=28, weight=ft.FontWeight.BOLD, color="#4B0082"), padding=10),
                id_box, pass_box, err_txt,
                ft.Row([
                    ft.Button(content=ft.Text("חזרה"), width=150, on_click=go_back),
                    ft.Button(content=ft.Text("כניסה"), width=150, bgcolor=ft.Colors.GREEN, color=ft.Colors.WHITE, on_click=handle_login)
                ], alignment=ft.MainAxisAlignment.CENTER)
            ])

        elif screen == "register_form":
            err_txt = ft.Text(color=ft.Colors.RED, bgcolor=ft.Colors.TRANSPARENT)
            name_box = ft.TextField(label="שם משתמש:", width=350, rtl=True, bgcolor=ft.Colors.with_opacity(0.9, ft.Colors.WHITE))
            email_box = ft.TextField(label="אימייל:", width=350, rtl=True, bgcolor=ft.Colors.with_opacity(0.9, ft.Colors.WHITE))
            pass_box = ft.TextField(label="סיסמה:", password=True, can_reveal_password=True, width=350, rtl=True, bgcolor=ft.Colors.with_opacity(0.9, ft.Colors.WHITE))
            pass_conf = ft.TextField(label="אימות סיסמה:", password=True, can_reveal_password=True, width=350, rtl=True, bgcolor=ft.Colors.with_opacity(0.9, ft.Colors.WHITE))

            def handle_register(e):
                if not name_box.value or not email_box.value or not pass_box.value: err_txt.value = "יש למלא את כל השדות!"
                elif pass_box.value != pass_conf.value: err_txt.value = "הסיסמאות אינן תואמות!"
                elif "@" not in email_box.value: err_txt.value = "נא להזין כתובת אימייל תקינה!"
                elif backend.register(name_box.value, email_box.value, pass_box.value): render("after_register_step")
                else: err_txt.value = "שגיאה בהרשמה. ייתכן והאימייל או השם תפוסים."
                page.update()

            content.controls.extend([
                ft.Container(content=ft.Text("הרשמה למערכת", size=28, weight=ft.FontWeight.BOLD, color="#f57c00"), padding=10),
                name_box, email_box, pass_box, pass_conf, err_txt,
                ft.Row([
                    ft.Button(content=ft.Text("חזרה"), width=150, on_click=go_back),
                    ft.Button(content=ft.Text("צור משתמש"), width=150, bgcolor=ft.Colors.AMBER_800, color=ft.Colors.WHITE, on_click=handle_register)
                ], alignment=ft.MainAxisAlignment.CENTER)
            ])

        elif screen == "after_register_step":
            new_user = backend.last_registered_user
            content.controls.extend([
                ft.Container(content=ft.Text("2Where", size=24, color=ft.Colors.WHITE), bgcolor="#4B0082", padding=20, border_radius=15),
                ft.Container(
                    content=ft.Column([
                        ft.Text(f"היי {new_user}!", size=32, color=ft.Colors.BLUE_800, weight=ft.FontWeight.BOLD),
                        ft.Text("נרשמת בהצלחה למערכת.", size=18)
                    ], horizontal_alignment=ft.CrossAxisAlignment.CENTER),
                    bgcolor=ft.Colors.BLUE_50, padding=40, border_radius=15, margin=20
                ),
                ft.Button(content=ft.Text("להתחבר עכשיו"), width=300, height=55, bgcolor=ft.Colors.BLUE_600, color=ft.Colors.WHITE, on_click=lambda _: render("login_form"))
            ])

        elif screen == "friends":
            username = backend.user_session["name"]
            
            if username == "אורח" or not username:
                content.controls.extend([
                    ft.Container(
                        content=ft.Text("משתמשים אורחים לא יכולים לנהל חברים. נא להתחבר למערכת.", color=ft.Colors.RED, size=18, weight=ft.FontWeight.BOLD),
                        padding=15, margin=20
                    ),
                    ft.Row([
                        ft.Button(content=ft.Text("התחבר עכשיו"), on_click=lambda _: render("login_form"), bgcolor=ft.Colors.BLUE_600, color=ft.Colors.WHITE),
                        ft.Button(content=ft.Text("חזרה"), on_click=go_back, bgcolor=ft.Colors.WHITE)
                    ], alignment=ft.MainAxisAlignment.CENTER)
                ])
                return content
                
            add_friend_input = ft.TextField(label="הזן שם משתמש לחיפוש...", width=200, rtl=True, bgcolor=ft.Colors.WHITE)
            request_msg = ft.Text(value="", size=14, weight=ft.FontWeight.BOLD)
            
            def on_add_friend(e):
                target = add_friend_input.value.strip()
                if not target: return
                success, msg = backend.send_friend_request(target)
                
                page.snack_bar = ft.SnackBar(
                    content=ft.Text(msg, color=ft.Colors.WHITE, weight=ft.FontWeight.BOLD),
                    bgcolor=ft.Colors.GREEN if success else ft.Colors.RED,
                    duration=3000
                )
                page.snack_bar.open = True
                
                request_msg.value = msg
                request_msg.color = ft.Colors.GREEN_700 if success else ft.Colors.RED_700
                
                if success: add_friend_input.value = ""
                page.update()
                
            add_btn = ft.Button(content=ft.Text("שלח בקשה"), bgcolor=ft.Colors.BLUE_600, color=ft.Colors.WHITE, on_click=on_add_friend)
            
            add_section = ft.Container(
                content=ft.Column([
                    ft.Text("הוספת חבר חדש", size=18, weight=ft.FontWeight.BOLD),
                    ft.Row([add_friend_input, add_btn], wrap=True, alignment=ft.MainAxisAlignment.CENTER),
                    request_msg
                ], horizontal_alignment=ft.CrossAxisAlignment.CENTER),
                padding=20, border_radius=10, bgcolor=ft.Colors.with_opacity(0.95, ft.Colors.WHITE), margin=10, width=page.width
            )

            pending, friends = backend.get_friends_data()
            
            pending_col = ft.Column()
            def create_request_handler(target, accept):
                def handler(e):
                    backend.handle_friend_request(target, accept)
                    render("friends")
                return handler

            if pending:
                pending_col.controls.append(ft.Text("בקשות חברות ממתינות:", weight=ft.FontWeight.BOLD, color=ft.Colors.ORANGE_800))
                for req in pending:
                    req_row = ft.Container(
                        content=ft.Row([
                            ft.Text(req, weight=ft.FontWeight.BOLD, size=16),
                            ft.Row([
                                ft.IconButton(icon=ft.Icons.CHECK, icon_color=ft.Colors.GREEN, on_click=create_request_handler(req, True), tooltip="אשר בקשה"),
                                ft.IconButton(icon=ft.Icons.CLOSE, icon_color=ft.Colors.RED, on_click=create_request_handler(req, False), tooltip="דחה בקשה")
                            ])
                        ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
                        bgcolor=ft.Colors.ORANGE_50, padding=10, border_radius=8, margin=5
                    )
                    pending_col.controls.append(req_row)

            friends_col = ft.Column()
            def create_remove_handler(target):
                def handler(e):
                    backend.remove_friend(target)
                    render("friends")
                return handler

            if not friends:
                friends_col.controls.append(ft.Text("עדיין אין לך חברים ברשימה."))
            else:
                for friend_obj in friends:
                    f_name = friend_obj["name"]
                    f_avatar = friend_obj["avatar"]
                    
                    if f_avatar:
                        avatar_ui = ft.CircleAvatar(foreground_image_url=f_avatar, radius=16)
                    else:
                        avatar_ui = ft.CircleAvatar(content=ft.Text(f_name[0].upper(), size=12, color=ft.Colors.WHITE), bgcolor=ft.Colors.GREY, radius=16)
                        
                    friend_row = ft.Container(
                        content=ft.Row([
                            ft.Row([avatar_ui, ft.Text(f_name, weight=ft.FontWeight.BOLD, size=16)]),
                            ft.IconButton(icon=ft.Icons.PERSON_REMOVE, icon_color=ft.Colors.RED_400, on_click=create_remove_handler(f_name), tooltip="הסר חבר")
                        ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
                        bgcolor=ft.Colors.BLUE_50, padding=10, border_radius=8, margin=5
                    )
                    friends_col.controls.append(friend_row)

            friends_section = ft.Container(
                content=ft.Column([
                    ft.Text("רשימת החברים שלי", size=18, weight=ft.FontWeight.BOLD),
                    pending_col,
                    ft.Divider(color=ft.Colors.TRANSPARENT, height=10),
                    friends_col
                ]),
                padding=20, border_radius=10, bgcolor=ft.Colors.with_opacity(0.95, ft.Colors.WHITE), margin=10, width=page.width
            )

            content.controls.extend([
                ft.Container(content=ft.Text("החברים שלי", size=24, color="#4B0082", weight=ft.FontWeight.BOLD), padding=10),
                add_section,
                friends_section,
                ft.Button(content=ft.Text("➔ חזרה"), on_click=go_back, bgcolor=ft.Colors.WHITE)
            ])

        elif screen == "personal_area":
            username = backend.user_session["name"]
            if username == "אורח" or not username:
                content.controls.extend([
                    ft.Container(
                        content=ft.Text("משתמשים אורחים לא יכולים לשמור נתונים. נא להתחבר למערכת.", color=ft.Colors.RED, size=18, weight=ft.FontWeight.BOLD),
                        padding=15,
                        margin=20
                    ),
                    ft.Row([
                        ft.Button(content=ft.Text("התחבר עכשיו"), on_click=lambda _: render("login_form"), bgcolor=ft.Colors.BLUE_600, color=ft.Colors.WHITE),
                        ft.Button(content=ft.Text("חזרה"), on_click=go_back, bgcolor=ft.Colors.WHITE)
                    ], alignment=ft.MainAxisAlignment.CENTER)
                ])
                return content

            avatar_url = backend.user_session.get("avatar_url", "")

            if avatar_url:
                avatar_display = ft.Container(
                    content=ft.Image(src=avatar_url, fit="cover"),
                    width=120, height=120, border_radius=60, clip_behavior=ft.ClipBehavior.HARD_EDGE
                )
            else:
                avatar_display = ft.CircleAvatar(content=ft.Text(username[0].upper(), size=40, color=ft.Colors.WHITE), radius=60, bgcolor=ft.Colors.GREY)

            upload_btn = ft.Button(
                content=ft.Text("העלה מהגלריה"),
                icon=ft.Icons.PHOTO_LIBRARY,
                on_click=lambda _: file_picker.pick_files(allow_multiple=False, file_type=ft.FilePickerFileType.IMAGE),
                bgcolor=ft.Colors.WHITE
            )

            url_input = ft.TextField(value=avatar_url, label="או הדבק קישור (URL)...", width=250, rtl=True, bgcolor=ft.Colors.WHITE)
            btn_save_link = ft.Button(content=ft.Text("שמור"), bgcolor=ft.Colors.BLUE_600, color=ft.Colors.WHITE, on_click=lambda e: (backend.update_avatar(url_input.value), render("personal_area")))
            
            avatar_input_col = ft.Column([
                upload_btn,
                ft.Text("או", weight=ft.FontWeight.BOLD, color=ft.Colors.GREY_600),
                ft.Row([url_input, btn_save_link], alignment=ft.MainAxisAlignment.CENTER, wrap=True)
            ], horizontal_alignment=ft.CrossAxisAlignment.CENTER)

            avatar_section = ft.Container(
                content=ft.Column([
                    ft.Text("תמונת פרופיל", size=18, weight=ft.FontWeight.BOLD),
                    avatar_display,
                    avatar_input_col
                ], horizontal_alignment=ft.CrossAxisAlignment.CENTER),
                padding=20, border_radius=10, bgcolor=ft.Colors.with_opacity(0.95, ft.Colors.WHITE)
            )

            inv_people = {v: k for k, v in backend.people_map.items()}
            inv_budget = {v: k for k, v in backend.budget_options.items()}
            
            pref_area = ft.Dropdown(options=[ft.dropdown.Option(key=a, text=a) for a in backend.areas], value=backend.user_session.get("area", "אילת"), label="אזור מועדף", width=200, bgcolor=ft.Colors.WHITE)
            pref_budget = ft.Dropdown(options=[ft.dropdown.Option(key=k, text=k) for k in backend.budget_options.keys()], value=inv_budget.get(backend.user_session.get("budget", 1000), 'ללא הגבלה'), label="תקציב מקסימלי", width=200, bgcolor=ft.Colors.WHITE)
            pref_people = ft.Dropdown(options=[ft.dropdown.Option(key=k, text=k) for k in backend.people_map.keys()], value=inv_people.get(backend.user_session.get("people_count", 4), '3-5'), label="כמות אנשים", width=200, bgcolor=ft.Colors.WHITE)

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
                padding=20, border_radius=10, bgcolor=ft.Colors.with_opacity(0.95, ft.Colors.WHITE)
            )

            events_col = ft.Column()
            my_events, my_invites = backend.get_my_events_and_invites()
            
            if not my_events and not my_invites:
                events_col.controls.append(ft.Text("אין אירועים או הזמנות כרגע."))
            else:
                if my_events:
                    events_col.controls.append(ft.Text("אירועים שיזמתי:", weight=ft.FontWeight.BOLD, color=ft.Colors.BLUE_800))
                    for ev in my_events:
                        invited_str = ", ".join(ev['invited']) if ev['invited'] else "אף אחד"
                        events_col.controls.append(
                            ft.Container(
                                content=ft.Column([
                                    ft.Text(f"📍 {ev['activity']} | 🕒 {ev['date_time']}", weight=ft.FontWeight.BOLD),
                                    ft.Text(f"מוזמנים: {invited_str}", size=14)
                                ]),
                                bgcolor=ft.Colors.BLUE_50, padding=10, border_radius=8, margin=5, width=page.width
                            )
                        )
                if my_invites:
                    events_col.controls.append(ft.Text("הזמנות שקיבלתי:", weight=ft.FontWeight.BOLD, color=ft.Colors.ORANGE_800))
                    for inv in my_invites:
                        events_col.controls.append(
                            ft.Container(
                                content=ft.Column([
                                    ft.Text(f"📍 {inv['activity']} (מאת: {inv['host']})", weight=ft.FontWeight.BOLD),
                                    ft.Text(f"🕒 {inv['date_time']}"),
                                    ft.Text(f"הודעה: {inv['note']}", size=14, italic=True, color=ft.Colors.GREY_700) if inv['note'] else ft.Container()
                                ]),
                                bgcolor=ft.Colors.ORANGE_50, padding=10, border_radius=8, margin=5, width=page.width
                            )
                        )

            events_section = ft.Container(
                content=ft.Column([ft.Text("האירועים וההזמנות שלי", size=18, weight=ft.FontWeight.BOLD), events_col]),
                padding=20, border_radius=10, bgcolor=ft.Colors.with_opacity(0.95, ft.Colors.WHITE), width=page.width
            )

            fav_col = ft.Column()
            favorites = backend.get_user_favorites()
            if not favorites:
                fav_col.controls.append(ft.Text("עדיין אין לך פעילויות במועדפים."))
            else:
                for act in backend.activities_db.values():
                    if act['name'] in favorites:
                        def make_go_to_details(selected_item):
                            def go_to_details(e):
                                backend.current_event = selected_item
                                render("event_details")
                            return go_to_details

                        clickable_fav = ft.Container(
                            content=ft.Row([
                                ft.Text(f"❤️ {act['name']}", size=16, color="#4B0082", weight=ft.FontWeight.BOLD),
                                ft.Text(f" - {act['price']} ₪", size=16)
                            ]),
                            on_click=make_go_to_details(act),
                            ink=True,
                            padding=8,
                            border_radius=8,
                            bgcolor=ft.Colors.with_opacity(0.5, ft.Colors.BLUE_50)
                        )
                        fav_col.controls.append(clickable_fav)

            favs_section = ft.Container(
                content=ft.Column([ft.Text("המועדפים שלי", size=18, weight=ft.FontWeight.BOLD), fav_col]),
                padding=20, border_radius=10, bgcolor=ft.Colors.with_opacity(0.95, ft.Colors.WHITE), width=page.width
            )

            content.controls.extend([
                ft.Container(content=ft.Text(f"אזור אישי - {username}", size=24, color="#4B0082"), padding=5),
                avatar_section, prefs_section, events_section, favs_section,
                ft.Button(content=ft.Text("➔ חזרה"), on_click=go_back, bgcolor=ft.Colors.WHITE)
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
                bgcolor=ft.Colors.WHITE
            )
            budget_dd = ft.Dropdown(
                options=[ft.dropdown.Option(key=k, text=k) for k in backend.budget_options.keys()],
                value=inv_budget.get(backend.user_session['budget'], 'ללא הגבלה'),
                width=300,
                bgcolor=ft.Colors.WHITE
            )
            area_dd = ft.Dropdown(
                options=[ft.dropdown.Option(key=a, text=a) for a in backend.areas],
                value=backend.user_session['area'],
                width=300,
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
                padding=8
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
                bgcolor=ft.Colors.with_opacity(0.9, ft.Colors.BLUE_50), padding=15, border_radius=8, margin=15
            )
            content.controls.append(filter_row)

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
                user_favorites = backend.get_user_favorites()

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

                        title_btn = ft.Container(
                            content=ft.Text(
                                item.get('short_headline', item['name']),
                                size=18,
                                weight=ft.FontWeight.W_900,
                                color=ft.Colors.WHITE,
                                max_lines=2,
                                overflow=ft.TextOverflow.ELLIPSIS,
                                text_align=ft.TextAlign.CENTER
                            ),
                            on_click=make_go_to_details(item),
                            alignment=ft.Alignment(0, 0),
                            expand=True,
                            ink=True,
                            bgcolor="#343a40",
                            border_radius=30,
                            padding=10
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
                            is_now_fav = act_name in backend.get_user_favorites()
                            e.control.icon = ft.Icons.FAVORITE if is_now_fav else ft.Icons.FAVORITE_BORDER
                            e.control.icon_color = ft.Colors.RED if is_now_fav else ft.Colors.GREY
                            page.update()

                        fav_btn.on_click = on_fav_click

                        rec_price = item.get('recommended_price', item['price'] + int(item['price'] * 0.15))
                        
                        price_tag = ft.Container(
                            content=ft.Text(f"{item['price']} ₪", color="#2e7d32", size=16, weight=ft.FontWeight.BOLD),
                            bgcolor="#99e89f", padding=8,
                            border_radius=20
                        )
                        rec_price_text = ft.Text(f"מחיר מומלץ: {rec_price} ₪", size=11, color=ft.Colors.GREY_600)

                        price_section = ft.Column(
                            controls=[price_tag, rec_price_text],
                            spacing=2,
                            horizontal_alignment=ft.CrossAxisAlignment.CENTER
                        )

                        img_box = ft.Container(
                            content=ft.Image(src=item['image_url'], fit="cover"),
                            width=140, height=120, border_radius=8,
                            clip_behavior=ft.ClipBehavior.HARD_EDGE
                        )

                        top_row = ft.Row([
                            title_btn,
                            price_section
                        ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN, vertical_alignment=ft.CrossAxisAlignment.START)

                        address_btn = ft.Container(
                            content=ft.Text(f"📍 {item['address']}", color=ft.Colors.RED_700, size=14, weight=ft.FontWeight.BOLD),
                            on_click=make_open_map(item),
                            ink=True,
                            border_radius=5,
                            padding=2
                        )

                        details_col = ft.Column([
                            top_row,
                            address_btn,
                            ft.Text(item.get('short_description', item['desc']), size=14, max_lines=2, overflow=ft.TextOverflow.ELLIPSIS),
                            fav_btn
                        ], expand=True, margin=10)

                        card_row = ft.Row([img_box, details_col], alignment=ft.MainAxisAlignment.START, vertical_alignment=ft.CrossAxisAlignment.START)

                        card_container = ft.Container(
                            content=card_row,
                            border_radius=12, padding=15, margin=15,
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

            content.controls.append(ft.Button(content=ft.Text("➔ חזרה"), on_click=go_back, bgcolor=ft.Colors.WHITE))

        elif screen == "event_details":
            content.scroll = None
            item = backend.current_event
            if not item: return

            username = backend.user_session["name"]
            user_favorites = backend.get_user_favorites() if username and username != "אורח" else []
            is_fav = item['name'] in user_favorites

            fav_btn = ft.IconButton(
                icon=ft.Icons.FAVORITE if is_fav else ft.Icons.FAVORITE_BORDER,
                icon_color=ft.Colors.RED if is_fav else ft.Colors.GREY,
                icon_size=30
            )

            def on_fav_click(e):
                if username == "אורח" or not username:
                    e.control.icon = ft.Icons.LOCK
                    page.update()
                    return
                backend.toggle_favorite(item['name'])
                is_now_fav = item['name'] in backend.get_user_favorites()
                e.control.icon = ft.Icons.FAVORITE if is_now_fav else ft.Icons.FAVORITE_BORDER
                e.control.icon_color = ft.Colors.RED if is_now_fav else ft.Colors.GREY
                page.update()
            
            fav_btn.on_click = on_fav_click

            # --- CUSTOM EVENT POPUP WITH FRIENDS ---
            date_input = ft.TextField(label="מתי הולכים? (לדוג' מחר ב-20:00)", rtl=True)
            note_input = ft.TextField(label="הודעה לחברים (אופציונלי)", multiline=True, rtl=True)
            
            friend_checkboxes = []
            friends_list_ui = ft.Column(scroll="auto", height=120)
            _, my_friends = backend.get_friends_data()
            
            if not my_friends:
                friends_list_ui.controls.append(ft.Text("אין לך עדיין חברים ברשימה.", color=ft.Colors.GREY))
            else:
                for f in my_friends:
                    cb = ft.Checkbox(label=f['name'], value=False)
                    friend_checkboxes.append(cb)
                    friends_list_ui.controls.append(cb)

            def submit_event(e):
                selected_friends = [cb.label for cb in friend_checkboxes if cb.value]
                dt = date_input.value.strip()
                note = note_input.value.strip()
                
                if not dt:
                    date_input.error_text = "חובה להזין תאריך ושעה"
                    page.update()
                    return
                
                backend.create_event(item['name'], dt, note, selected_friends)
                hide_popup()
                
                page.snack_bar = ft.SnackBar(
                    content=ft.Text("האירוע נוצר וההזמנות נשלחו למשתתפים!", color=ft.Colors.WHITE, weight=ft.FontWeight.BOLD),
                    bgcolor=ft.Colors.GREEN,
                    duration=3000
                )
                page.snack_bar.open = True
                page.update()

            popup_box = ft.Container(
                content=ft.Column([
                    ft.Text(f"יצירת אירוע - {item['name']}", size=20, weight=ft.FontWeight.BOLD, color=ft.Colors.BLUE_900),
                    date_input,
                    note_input,
                    ft.Text("את מי מהחברים להזמין?", weight=ft.FontWeight.BOLD),
                    ft.Container(content=friends_list_ui, padding=10, bgcolor=ft.Colors.BLUE_50, border_radius=8),
                    ft.Row([
                        ft.Button("ביטול", on_click=hide_popup, color=ft.Colors.RED),
                        ft.Button("צור אירוע", on_click=submit_event, bgcolor=ft.Colors.GREEN, color=ft.Colors.WHITE)
                    ], alignment=ft.MainAxisAlignment.END)
                ], tight=True),
                bgcolor=ft.Colors.WHITE,
                padding=25,
                border_radius=15,
                width=350
            )

            def handle_book(e):
                if username == "אורח" or not username:
                    page.snack_bar = ft.SnackBar(content=ft.Text("יש להתחבר למערכת כדי ליצור אירוע.", color=ft.Colors.WHITE), bgcolor=ft.Colors.RED)
                    page.snack_bar.open = True
                    page.update()
                    return
                
                date_input.value = ""
                date_input.error_text = None
                note_input.value = ""
                for cb in friend_checkboxes:
                    cb.value = False
                    
                show_popup(popup_box)

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
                bgcolor=ft.Colors.RED_50, padding=10, border_radius=20, alignment=ft.Alignment(1, 0),
                on_click=open_map,
                ink=True
            )

            rec_price = item.get('recommended_price', item['price'] + int(item['price'] * 0.15))
            
            price_tag = ft.Container(content=ft.Text(f"{item['price']} ₪ לאדם", color="#2e7d32", size=16, weight=ft.FontWeight.BOLD), bgcolor="#99e89f", padding=10, border_radius=20)
            rec_price_text = ft.Text(f"מחיר מומלץ: {rec_price} ₪", size=12, color=ft.Colors.GREY_600)
            
            price_section = ft.Column([price_tag, rec_price_text], spacing=2, horizontal_alignment=ft.CrossAxisAlignment.CENTER)

            scrollable_details = ft.Column(
                expand=True,
                scroll="auto",
                controls=[
                    ft.Container(
                        content=ft.Image(src=item['image_url'], fit="cover"),
                        width=page.width, height=250, border_radius=15,
                        shadow=ft.BoxShadow(blur_radius=16, color=ft.Colors.BLACK_26),
                        clip_behavior=ft.ClipBehavior.HARD_EDGE
                    ),
                    ft.Row([
                        ft.Container(
                            content=ft.Text(item['name'], size=24, weight=ft.FontWeight.W_800, color=ft.Colors.WHITE, text_align=ft.TextAlign.CENTER),
                            expand=True,
                            bgcolor=ft.Colors.BLACK,
                            border_radius=10,
                            padding=10,
                            alignment=ft.Alignment(0, 0)
                        ),
                        price_section
                    ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN, margin=15, vertical_alignment=ft.CrossAxisAlignment.CENTER),
                    
                    map_button,
                    
                    ft.Container(
                        content=ft.Column([
                            ft.Text("על הפעילות:", size=18, weight=ft.FontWeight.BOLD),
                            ft.Text(item['desc'], size=16, color=ft.Colors.GREY_800)
                        ]),
                        padding=10, margin=10, width=page.width
                    ),
                    
                    ft.Button(content=ft.Text("➔ חזרה"), on_click=go_back, margin=15, bgcolor=ft.Colors.WHITE)
                ]
            )

            sticky_bottom_bar = ft.Container(
                content=ft.Column([
                    ft.Row([
                        ft.Button(
                            content=ft.Text("📅 צור אירוע / הזמן מקום", size=18, weight=ft.FontWeight.BOLD),
                            bgcolor=ft.Colors.GREEN,
                            color=ft.Colors.WHITE,
                            height=60,
                            expand=True,
                            on_click=handle_book
                        ),
                        fav_btn
                    ], spacing=10)
                ], horizontal_alignment=ft.CrossAxisAlignment.CENTER),
                bgcolor=ft.Colors.with_opacity(0.98, ft.Colors.BLUE_50),
                padding=20,
                margin=0,
                border_radius=25,
                shadow=ft.BoxShadow(spread_radius=1, blur_radius=15, color=ft.Colors.BLACK_12, offset=ft.Offset(0, -3))
            )

            content.controls.extend([
                scrollable_details,
                sticky_bottom_bar
            ])

        return content

    page.add(main_layout)
    render("welcome")

ft.app(target=main, assets_dir="assets")
