# imports
from ursina import *
from ursina.prefabs.first_person_controller import FirstPersonController
from ursina.shaders import lit_with_shadows_shader
from ursina.prefabs.health_bar import HealthBar
import json
import math

# init app
app = Ursina()

# globals
random.seed(0)
Entity.default_shader = lit_with_shadows_shader
game_state = 'waiting_for_start'
player = None
enemy = None
player_health_bar = None
game_over_ui = None
waiting_text_entity = None

# scene setup
ground = Entity(model='plane', collider='box', scale=64, texture='grass', texture_scale=(4,4))
gun = Entity(model='cube', parent=camera, position=(.5,-.25,.25), scale=(.3,.2,1), origin_z=-.5, color=color.red, on_cooldown=False)
gun.muzzle_flash = Entity(parent=gun, z=1, world_scale=.5, model='quad', color=color.yellow, enabled=False)
shootables_parent = Entity()
mouse.traverse_target = shootables_parent
for i in range(16):
    Entity(model='cube', origin_y=-.5, scale=2, texture='brick', texture_scale=(1,2),
        x=random.uniform(-8,8),
        z=random.uniform(-8,8) + 8,
        collider='box',
        scale_y = random.uniform(2,3),
        color=color.hsv(0, 0, random.uniform(.9, 1))
        )

def update():
    global game_state

    # write a short game state report for the agent
    if player and enemy:
        player_y_rotation = player.rotation_y
        direction_vector = enemy.position - player.position
        angle_to_enemy_rad = math.atan2(direction_vector.x, direction_vector.z)
        angle_to_enemy_deg = math.degrees(angle_to_enemy_rad)
        aiming_error = angle_to_enemy_deg - player_y_rotation
        if aiming_error > 180: aiming_error -= 360
        if aiming_error < -180: aiming_error += 360
        hit_info = raycast(player.world_position + player.camera_pivot.up, camera.forward, distance=100, ignore=(player,))
        is_enemy_visible = True if hit_info.entity == enemy else False

        game_data = {
            "player_health": player.hp,
            "player_rotation_y": player_y_rotation,
            "enemy_health": enemy.hp,
            "distance_to_enemy": distance_xz(player.position, enemy.position),
            "is_enemy_visible": is_enemy_visible,
            "angle_to_enemy_error": aiming_error,
            "game_status": game_state,
        }
        try:
            with open("game_state.json", "w") as f:
                json.dump(game_data, f)
        except Exception:
            pass

    if game_state != 'playing':
        return

    if held_keys['left mouse']:
        shoot()

    if player.hp <= 0:
        game_state = 'lost'
        show_game_over_screen("YOU DIED")

def shoot():
    # simple fire with cooldown and muzzle flash
    if not gun.on_cooldown:
        gun.on_cooldown = True
        gun.muzzle_flash.enabled=True
        from ursina.prefabs.ursfx import ursfx
        ursfx([(0.0, 0.0), (0.1, 0.9), (0.15, 0.75), (0.3, 0.14), (0.6, 0.0)], volume=0.5, wave='noise', pitch=random.uniform(-13,-12), pitch_change=-12, speed=3.0)
        invoke(gun.muzzle_flash.disable, delay=.05)
        invoke(setattr, gun, 'on_cooldown', False, delay=.15)
        if mouse.hovered_entity and hasattr(mouse.hovered_entity, 'hp'):
            mouse.hovered_entity.hp -= 10
            mouse.hovered_entity.blink(color.red)

class Enemy(Entity):
    def __init__(self, **kwargs):
        super().__init__(parent=shootables_parent, model='cube', scale_y=2, origin_y=-.5, color=color.light_gray, collider='box', **kwargs)
        self.health_bar = Entity(parent=self, y=1.2, model='cube', color=color.red, world_scale=(1.5,.1,.1))
        self.max_hp = 100
        self._hp = self.max_hp
        self.attack_cooldown = False
    
    def update(self):
        if game_state != 'playing': return
        dist = distance_xz(player.position, self.position)
        if dist > 40: return
        self.health_bar.alpha = max(0, self.health_bar.alpha - time.dt)
        self.look_at_2d(player.position, 'y')
        hit_info = raycast(self.world_position + Vec3(0,1,0), self.forward, 30, ignore=(self,))
        if hit_info.entity == player:
            if dist > 2:
                self.position += self.forward * time.dt * 5
            else:
                if not self.attack_cooldown:
                    player.hp -= 20
                    if player_health_bar: player_health_bar.value = player.hp
                    self.attack_cooldown = True
                    invoke(setattr, self, 'attack_cooldown', False, delay=1)

    @property
    def hp(self): return self._hp

    @hp.setter
    def hp(self, value):
        global game_state
        self._hp = value
        if value <= 0:
            if game_state == 'playing':
                game_state = 'won'
                show_game_over_screen("YOU WIN!")
            destroy(self)
            return
        self.health_bar.world_scale_x = self.hp / self.max_hp * 1.5
        self.health_bar.alpha = 1

def start_game():
    global player, enemy, player_health_bar, game_state, game_over_ui, waiting_text_entity
    if player: destroy(player)
    if enemy: destroy(enemy)
    if player_health_bar: destroy(player_health_bar)
    if game_over_ui: destroy(game_over_ui)
    if waiting_text_entity: destroy(waiting_text_entity)
    player = FirstPersonController(model='cube', z=-10, color=color.orange, origin_y=-.5, speed=8, collider='box')
    player.collider = BoxCollider(player, Vec3(0,1,0), Vec3(1,2,1))
    player.max_hp = 100
    player.hp = player.max_hp
    player.enable()
    player_health_bar = HealthBar(bar_color=color.lime.tint(-.25), roundness=.5, value=player.hp, max_value=player.max_hp)
    enemy = Enemy(x=8, z=8)
    gun.enable()
    mouse.locked = True
    game_state = 'waiting_for_start'
    game_over_ui = None
    waiting_text_entity = Text("WAITING FOR AI AGENT...", origin=(0,0), scale=2, color=color.orange, y=.2, parent=camera.ui)

def show_game_over_screen(message):
    global game_over_ui
    if player: player.disable()
    if gun: gun.disable()
    mouse.locked = False
    game_over_ui = Entity(parent=camera.ui, name='game_over_ui')
    text_color = color.red if "DIED" in message else color.azure
    Text(message, parent=game_over_ui, scale=5, origin=(0, 0), background=True, color=text_color)
    Text("Press 'R' to Restart or 'Q' to Quit", parent=game_over_ui, y=-.15, scale=2, origin=(0, 0))

def input(key):
    global game_state, waiting_text_entity
    if game_state == 'waiting_for_start' and key == 'g':
        game_state = 'playing'
        if waiting_text_entity: destroy(waiting_text_entity)
        return
    if key == 'q': application.quit()
    if game_state != 'playing' and key == 'r': start_game()
    if key == 'tab':
        editor_camera.enabled = not editor_camera.enabled
        player.visible_self = not editor_camera.enabled
        player.cursor.enabled = not editor_camera.enabled
        gun.enabled = not editor_camera.enabled
        mouse.locked = not editor_camera.enabled
        application.paused = editor_camera.enabled

# final setup
editor_camera = EditorCamera(enabled=False, ignore_paused=True)
pause_handler = Entity(ignore_paused=True, input=input)
sun = DirectionalLight()
sun.look_at(Vec3(1,-1,-1))
Sky()
start_game()
app.run()