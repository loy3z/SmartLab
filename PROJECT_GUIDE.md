# SmartLab: start here

SmartLab helps people book laboratory rooms and equipment. Understand these three workflows first:

1. **Book:** check training → choose a resource and time → submit a request → follow its status in My Bookings.
2. **Review:** staff check training evidence and booking requests. An approved booking is confirmed; a waitlisted request still needs a place.
3. **Manage:** a Manager maintains resources, staff accounts, training instructions and contact details.

Rooms and equipment are booked separately. Booking a room does not reserve its equipment.

## Which account does what?

| Role | Main job | Starting page |
| --- | --- | --- |
| Student | Submit training evidence and manage personal bookings | Dashboard |
| Admin | Review training and booking requests | Today |
| Manager | Do the Admin's work and manage the lab's setup | Today |

Staff can also make bookings. Booking rules still apply, and staff cannot approve requests they created or requests for themselves.

## Find the right page

The staff menu groups pages by the task you are doing. Students see their personal booking pages.

| Menu group | Pages | Use them for |
| --- | --- | --- |
| Personal bookings | Book a Resource, My Bookings, Induction & Training | Make bookings, follow requests and submit training evidence |
| Daily work | Today, Qualification Review, Booking Review | See outstanding work, review evidence and decide requests |
| Lab management — Manager only | Lab Overview (Manager home), Room Management, Resources, User Management, Lab Setup | Run the lab, see what only a Manager decides, and keep internal equipment details |
| Records & calendar | Booking Records, Calendar Sync | Look up history (Admins: last 7 days; Managers: everything and usage statistics), export records and check Outlook sync |

Four similarly named pages have different jobs:

- **Book a Resource:** choose something to use and request a time.
- **Resources:** add or edit the rooms and equipment people can book.
- **Room Management:** open or close rooms and handle confirmed room bookings.
- **Lab Setup:** maintain training requirements, training instructions and contact details.

**Calendar Sync is a development/support view.** Students subscribe to their calendar from My Bookings.

## Follow one request

Submit a booking → wait for approval or a place → receive approval → check in during the displayed window.

- Read the request's status and deadline in **My Bookings**. Submission alone does not confirm a booking.
- If a time is taken, the request joins the waitlist. When a place opens, the next eligible request moves to approval.
- Use **Change time** to request a different time for a future approved booking. Read the displayed status of both the original booking and the change request.
- Staff handle requests in **Booking Review**. **Qualification Review** handles training evidence separately.

The [current business rules](backend/README.md) explain deadlines, limits and exceptions. Use that document for exact policy values; this guide explains where to go.

## 通知和公告（Sprint 3，1.19.0）

从侧栏 **Notifications** 设置个人更新：五类分别选择 **In the bell** 和 **By email**，自动保存。只开邮件时铃铛不显示该条，邮件未在网站启用时该列不可操作，并显示为不勾选（保存的选择不变，启用后恢复）。Account 页的 **Notification settings** 也可进入。

所有人的首页顶部显示生效公告和发布人署名。员工从 **Daily work → Announcements** 发布公告：Title、Message 必填，Remove at 可选，按悉尼时间填写。作者能修改和下架自己的，Manager 还能下架别人的。已结束公告仍可在管理页查到。

Manager 在 **Room management** 维修或关闭房间时，原因自动成为状态公告，可填预计恢复时间 **Expected back**。到时间不会自行重开；由 Manager 选择 Reopen，公告才自动下架。状态公告标有 **From room status**，不能当作手动公告编辑。设备的相同规则已在接口实现，设备状态的界面入口仍待后续任务。

## Where does the code live?

You do not need to read every folder to understand one feature.

| Folder | Responsibility |
| --- | --- |
| `frontend/src/app/` | Navigation, page routes and the shared layout |
| `frontend/src/features/` | The pages and interactions for booking, training, reviews and management |
| `backend/booking/services/` | Booking rules and business actions |
| `backend/booking/postgres.py` and `backend/database/` | Persistent storage and database migrations |

For a specific feature, start at its page, follow its API call, then read the matching backend service. [ARCHITECTURE.md](ARCHITECTURE.md) is the detailed map. [SPRINT3.md](SPRINT3.md) lists Sprint 3 additions. [CHANGELOG.md](CHANGELOG.md) explains what changed between versions.

## Run the existing local setup

Keep both terminals open. These commands assume the existing dependencies and local database have already been set up.

**Backend — PowerShell, with PostgreSQL running:**

```powershell
cd C:\Users\loy\Desktop\9900\team-repo\backend
powershell -ExecutionPolicy Bypass -File .\start-backend.ps1
```

Enter the local PostgreSQL password when prompted. This local helper applies database migrations and starts the backend. It is not tracked in Git; another computer should follow [the database setup instructions](backend/database/README.md).

For a temporary demo, add `-Memory`. Demo changes disappear when that backend stops.

**Frontend — another PowerShell terminal:**

```powershell
cd C:\Users\loy\Desktop\9900\team-repo\frontend
npm.cmd run dev
```

Open the URL shown by the frontend, usually `http://localhost:5173`.

In demo mode, students can use `z1000001` or `z1000002` through University sign-in. Staff sign-in uses `z9000001` for Admin or `z9000002` for Manager, with the demo password `123`. These are demo identities, not production credentials.
