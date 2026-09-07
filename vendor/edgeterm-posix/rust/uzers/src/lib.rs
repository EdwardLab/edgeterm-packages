#![allow(non_camel_case_types)]

use std::ffi::{OsStr, OsString};
use std::sync::Arc;

pub type uid_t = u32;
pub type gid_t = u32;

#[derive(Clone, Debug)]
pub struct User {
    uid: uid_t,
    name: OsString,
    primary_group: gid_t,
}

impl User {
    pub fn new<S: AsRef<OsStr> + ?Sized>(uid: uid_t, name: &S, primary_group: gid_t) -> Self {
        Self {
            uid,
            name: name.as_ref().to_os_string(),
            primary_group,
        }
    }

    pub fn uid(&self) -> uid_t {
        self.uid
    }

    pub fn name(&self) -> &OsStr {
        &self.name
    }

    pub fn primary_group_id(&self) -> gid_t {
        self.primary_group
    }
}

#[derive(Clone, Debug)]
pub struct Group {
    gid: gid_t,
    name: OsString,
    members: Vec<OsString>,
}

impl Group {
    pub fn new<S: AsRef<OsStr> + ?Sized>(gid: gid_t, name: &S) -> Self {
        Self {
            gid,
            name: name.as_ref().to_os_string(),
            members: Vec::new(),
        }
    }

    pub fn gid(&self) -> gid_t {
        self.gid
    }

    pub fn name(&self) -> &OsStr {
        &self.name
    }
}

pub trait Users {
    fn get_user_by_uid(&self, uid: uid_t) -> Option<Arc<User>>;
    fn get_user_by_name<S: AsRef<OsStr> + ?Sized>(&self, username: &S) -> Option<Arc<User>>;
    fn get_current_uid(&self) -> uid_t;
    fn get_current_username(&self) -> Option<Arc<OsStr>>;
    fn get_effective_uid(&self) -> uid_t;
    fn get_effective_username(&self) -> Option<Arc<OsStr>>;
}

pub trait Groups {
    fn get_group_by_gid(&self, gid: gid_t) -> Option<Arc<Group>>;
    fn get_group_by_name<S: AsRef<OsStr> + ?Sized>(&self, group: &S) -> Option<Arc<Group>>;
    fn get_current_gid(&self) -> gid_t;
    fn get_current_groupname(&self) -> Option<Arc<OsStr>>;
    fn get_effective_gid(&self) -> gid_t;
    fn get_effective_groupname(&self) -> Option<Arc<OsStr>>;
}

#[derive(Default)]
pub struct UsersCache;

impl UsersCache {
    pub fn new() -> Self {
        Self
    }
}

fn root_user() -> Arc<User> {
    Arc::new(User::new(0, OsStr::new("root"), 0))
}

fn root_group() -> Arc<Group> {
    Arc::new(Group::new(0, OsStr::new("root")))
}

impl Users for UsersCache {
    fn get_user_by_uid(&self, uid: uid_t) -> Option<Arc<User>> {
        (uid == 0).then(root_user)
    }

    fn get_user_by_name<S: AsRef<OsStr> + ?Sized>(&self, username: &S) -> Option<Arc<User>> {
        (username.as_ref() == OsStr::new("root")).then(root_user)
    }

    fn get_current_uid(&self) -> uid_t {
        0
    }

    fn get_current_username(&self) -> Option<Arc<OsStr>> {
        Some(Arc::from(OsStr::new("root")))
    }

    fn get_effective_uid(&self) -> uid_t {
        0
    }

    fn get_effective_username(&self) -> Option<Arc<OsStr>> {
        self.get_current_username()
    }
}

impl Groups for UsersCache {
    fn get_group_by_gid(&self, gid: gid_t) -> Option<Arc<Group>> {
        (gid == 0).then(root_group)
    }

    fn get_group_by_name<S: AsRef<OsStr> + ?Sized>(&self, group: &S) -> Option<Arc<Group>> {
        (group.as_ref() == OsStr::new("root")).then(root_group)
    }

    fn get_current_gid(&self) -> gid_t {
        0
    }

    fn get_current_groupname(&self) -> Option<Arc<OsStr>> {
        Some(Arc::from(OsStr::new("root")))
    }

    fn get_effective_gid(&self) -> gid_t {
        0
    }

    fn get_effective_groupname(&self) -> Option<Arc<OsStr>> {
        self.get_current_groupname()
    }
}

pub mod os {
    pub mod unix {
        use std::ffi::{OsStr, OsString};

        use crate::Group;

        pub trait GroupExt {
            fn members(&self) -> &[OsString];
            fn add_member<S: AsRef<OsStr> + ?Sized>(self, member: &S) -> Self;
        }

        impl GroupExt for Group {
            fn members(&self) -> &[OsString] {
                &self.members
            }

            fn add_member<S: AsRef<OsStr> + ?Sized>(mut self, member: &S) -> Self {
                self.members.push(member.as_ref().to_os_string());
                self
            }
        }
    }
}
