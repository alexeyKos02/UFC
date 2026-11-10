import { createRouter, createWebHistory, type RouteRecordRaw } from 'vue-router'
import { currentUser, isOwner, isStaff, restoreSession } from './auth'

declare module 'vue-router' {
  interface RouteMeta {
    public?: boolean
    staff?: boolean
    owner?: boolean
  }
}

const routes: RouteRecordRaw[] = [
  { path: '/login', component: () => import('./views/LoginView.vue'), meta: { public: true } },
  { path: '/register', component: () => import('./views/RegisterView.vue'), meta: { public: true } },
  { path: '/', component: () => import('./views/HomeView.vue') },
  { path: '/tournaments', component: () => import('./views/TournamentsView.vue') },
  { path: '/tournaments/:id', component: () => import('./views/TournamentView.vue'), props: true },
  { path: '/league', component: () => import('./views/LeagueView.vue') },
  { path: '/players/:id', component: () => import('./views/PlayerView.vue'), props: true },
  { path: '/fights', component: () => import('./views/FightsView.vue') },
  { path: '/fights/new', component: () => import('./views/NewFightView.vue') },
  { path: '/fights/:id', component: () => import('./views/FightView.vue'), props: true },
  { path: '/my-fights', component: () => import('./views/MyFightsView.vue') },
  { path: '/belts', component: () => import('./views/BeltsView.vue') },
  { path: '/belts/:id', component: () => import('./views/BeltView.vue'), props: true },
  {
    path: '/admin',
    component: () => import('./views/admin/AdminLayout.vue'),
    meta: { staff: true },
    redirect: '/admin/tournaments',
    children: [
      { path: 'tournaments', component: () => import('./views/admin/AdminTournaments.vue') },
      { path: 'belts', component: () => import('./views/admin/AdminBelts.vue') },
      { path: 'title-fights', component: () => import('./views/admin/AdminTitleFights.vue') },
      { path: 'rating', component: () => import('./views/admin/AdminRating.vue') },
      { path: 'promos', component: () => import('./views/admin/AdminPromos.vue') },
      {
        path: 'users',
        component: () => import('./views/admin/AdminUsers.vue'),
        meta: { staff: true, owner: true },
      },
    ],
  },
  { path: '/:pathMatch(.*)*', component: () => import('./views/NotFoundView.vue') },
]

export const router = createRouter({
  history: createWebHistory(),
  routes,
  scrollBehavior: () => ({ top: 0 }),
})

router.beforeEach(async (to) => {
  await restoreSession()
  if (to.meta.public) {
    return currentUser.value ? '/' : true
  }
  if (!currentUser.value) {
    return { path: '/login', query: to.fullPath === '/' ? {} : { next: to.fullPath } }
  }
  if (to.meta.staff && !isStaff.value) return '/'
  if (to.meta.owner && !isOwner.value) return '/admin'
  return true
})
