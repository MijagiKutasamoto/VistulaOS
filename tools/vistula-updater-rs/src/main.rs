mod cinnamon;
mod commands;
mod config;
mod i18n;
mod pacman;
mod flatpak;

use iced::{
    executor, widget::{column, container, row, text, button, text_input, scrollable},
    Element, Settings, Application, Command, Length, Alignment,
};
use std::collections::HashMap;

pub fn main() -> iced::Result {
    VistulaUpdater::run(Settings::default())
}

#[derive(Debug, Clone, Copy, PartialEq)]
enum Tab {
    System,
    Flatpak,
    Settings,
}

#[derive(Debug, Clone)]
enum Message {
    TabChanged(Tab),
    // System tab
    CheckUpdates,
    UpdatesChecked(Result<Vec<pacman::PackageUpdate>, String>),
    UpdateSystem,
    SystemUpdated(Result<(), String>),
    // Flatpak tab
    SearchFlatpaks,
    SearchQueryChanged(String),
    FlatpaksFound(Result<Vec<flatpak::FlatpakApp>, String>),
    InstallFlatpak(String),
    FlatpakInstalled(Result<(), String>),
    ListInstalledFlatpaks,
    InstalledLoaded(Result<Vec<flatpak::FlatpakApp>, String>),
    // Settings tab
    LanguageChanged(String),
    ThemeChanged(String),
}

struct VistulaUpdater {
    current_tab: Tab,
    config: config::AppConfig,
    
    // System tab state
    available_updates: Vec<pacman::PackageUpdate>,
    checking_updates: bool,
    system_status: String,
    
    // Flatpak tab state
    flatpak_search_query: String,
    flatpak_search_results: Vec<flatpak::FlatpakApp>,
    installed_flatpaks: Vec<flatpak::FlatpakApp>,
    searching_flatpaks: bool,
    flatpak_status: String,
    
    // Settings state
    available_languages: Vec<String>,
}

impl iced::Application for VistulaUpdater {
    type Executor = executor::Default;
    type Message = Message;
    type Theme = iced::Theme;
    type Flags = ();

    fn new(_flags: Self::Flags) -> (Self, Command<Self::Message>) {
        let config = config::load_config().unwrap_or_default();
        let lang = config.language.clone();
        i18n::set_language(&lang);
        
        (
            VistulaUpdater {
                current_tab: Tab::System,
                config,
                available_updates: Vec::new(),
                checking_updates: false,
                system_status: i18n::t("sys.check"),
                flatpak_search_query: String::new(),
                flatpak_search_results: Vec::new(),
                installed_flatpaks: Vec::new(),
                searching_flatpaks: false,
                flatpak_status: String::new(),
                available_languages: vec!["en".to_string(), "pl".to_string()],
            },
            Command::none(),
        )
    }

    fn title(&self) -> String {
        i18n::t("app.title")
    }

    fn update(&mut self, message: Message) -> Command<Self::Message> {
        match message {
            Message::TabChanged(tab) => {
                self.current_tab = tab;
                match tab {
                    Tab::System => {
                        self.system_status = i18n::t("sys.status.checking");
                        self.checking_updates = true;
                        Command::perform(pacman::check_for_updates(), Message::UpdatesChecked)
                    }
                    Tab::Flatpak => {
                        self.flatpak_status = i18n::t("fp.status.loading_installed");
                        Command::perform(flatpak::list_installed(), Message::InstalledLoaded)
                    }
                    Tab::Settings => Command::none(),
                }
            }
            
            // System tab handlers
            Message::CheckUpdates => {
                self.checking_updates = true;
                self.system_status = i18n::t("sys.status.checking");
                Command::perform(pacman::check_for_updates(), Message::UpdatesChecked)
            }
            
            Message::UpdatesChecked(result) => {
                self.checking_updates = false;
                match result {
                    Ok(updates) => {
                        let count = updates.len();
                        self.available_updates = updates;
                        if count > 0 {
                            let mut args = HashMap::new();
                            args.insert("n", count.to_string());
                            self.system_status = i18n::t_with_args("sys.status.found", &args);
                        } else {
                            self.system_status = i18n::t("sys.status.updated");
                        }
                    }
                    Err(e) => {
                        self.system_status = format!("{}: {}", i18n::t("sys.status.check_error"), e);
                    }
                }
                Command::none()
            }
            
            Message::UpdateSystem => {
                self.system_status = i18n::t("sys.status.updating");
                self.checking_updates = true;
                Command::perform(pacman::update_system(), Message::SystemUpdated)
            }
            
            Message::SystemUpdated(result) => {
                self.checking_updates = false;
                match result {
                    Ok(_) => {
                        self.system_status = i18n::t("sys.status.updated");
                        self.available_updates.clear();
                    }
                    Err(e) => {
                        self.system_status = format!("{}: {}", i18n::t("sys.status.update_failed"), e);
                    }
                }
                Command::none()
            }
            
            // Flatpak tab handlers
            Message::SearchQueryChanged(query) => {
                self.flatpak_search_query = query;
                Command::none()
            }
            
            Message::SearchFlatpaks => {
                if self.flatpak_search_query.is_empty() {
                    self.flatpak_status = i18n::t("fp.status.type_query");
                    return Command::none();
                }
                self.searching_flatpaks = true;
                self.flatpak_status = i18n::t("fp.status.searching");
                let query = self.flatpak_search_query.clone();
                Command::perform(
                    async move {
                        flatpak::search(&query, "flathub").await
                    },
                    Message::FlatpaksFound,
                )
            }
            
            Message::FlatpaksFound(result) => {
                self.searching_flatpaks = false;
                match result {
                    Ok(apps) => {
                        let count = apps.len();
                        self.flatpak_search_results = apps;
                        let mut args = HashMap::new();
                        args.insert("n", count.to_string());
                        self.flatpak_status = i18n::t_with_args("fp.status.results", &args);
                    }
                    Err(e) => {
                        self.flatpak_status = format!("{}: {}", i18n::t("fp.status.search_error"), e);
                    }
                }
                Command::none()
            }
            
            Message::InstallFlatpak(appid) => {
                self.flatpak_status = i18n::t("fp.status.installing");
                self.searching_flatpaks = true;
                let app_id = appid.clone();
                Command::perform(
                    async move {
                        flatpak::install(&app_id).await
                    },
                    Message::FlatpakInstalled,
                )
            }
            
            Message::FlatpakInstalled(result) => {
                self.searching_flatpaks = false;
                match result {
                    Ok(_) => {
                        self.flatpak_status = i18n::t("fp.status.installed");
                    }
                    Err(e) => {
                        self.flatpak_status = format!("{}: {}", i18n::t("fp.status.install_failed"), e);
                    }
                }
                Command::none()
            }
            
            Message::ListInstalledFlatpaks => {
                self.flatpak_status = i18n::t("fp.status.loading_installed");
                Command::perform(flatpak::list_installed(), Message::InstalledLoaded)
            }
            
            Message::InstalledLoaded(result) => {
                match result {
                    Ok(apps) => {
                        self.installed_flatpaks = apps;
                        self.flatpak_status = String::new();
                    }
                    Err(e) => {
                        self.flatpak_status = format!("Error: {}", e);
                    }
                }
                Command::none()
            }
            
            // Settings handlers
            Message::LanguageChanged(lang) => {
                self.config.language = lang;
                i18n::set_language(&self.config.language);
                let _ = config::save_config(&self.config);
                Command::none()
            }
            
            Message::ThemeChanged(theme) => {
                self.config.theme = theme;
                let _ = config::save_config(&self.config);
                Command::none()
            }
        }
    }

    fn view(&self) -> Element<Message> {
        let tab_buttons = row![
            button(text(i18n::t("tab.system")))
                .on_press(Message::TabChanged(Tab::System)),
            button(text(i18n::t("tab.flatpak")))
                .on_press(Message::TabChanged(Tab::Flatpak)),
            button(text(i18n::t("tab.settings")))
                .on_press(Message::TabChanged(Tab::Settings)),
        ]
        .spacing(10);

        let content = match self.current_tab {
            Tab::System => self.view_system_tab(),
            Tab::Flatpak => self.view_flatpak_tab(),
            Tab::Settings => self.view_settings_tab(),
        };

        container(
            column![
                tab_buttons,
                content,
            ]
            .spacing(20)
            .padding(20)
        )
        .padding(10)
        .into()
    }
}

impl VistulaUpdater {
    fn view_system_tab(&self) -> Element<Message> {
        let check_btn = button(text(i18n::t("sys.check")))
            .on_press(Message::CheckUpdates);
        
        let update_btn = if !self.available_updates.is_empty() {
            button(text(i18n::t("sys.update")))
                .on_press(Message::UpdateSystem)
        } else {
            button(text(i18n::t("sys.update")))
        };

        let mut updates_list = column![];
        for update in &self.available_updates {
            let update_row = row![
                text(&update.name).width(Length::FillPortion(2)),
                text(&update.current_version).width(Length::FillPortion(1)),
                text("→"),
                text(&update.new_version).width(Length::FillPortion(1)),
            ]
            .spacing(10);
            updates_list = updates_list.push(update_row);
        }

        let status = text(&self.system_status);

        column![
            row![check_btn, update_btn].spacing(10),
            status,
            scrollable(
                column![
                    text(format!("{}:", i18n::t("sys.col.pkg")))
                        .width(Length::FillPortion(2)),
                    updates_list,
                ]
                .spacing(5)
            ).height(Length::Fill),
        ]
        .spacing(10)
        .into()
    }

    fn view_flatpak_tab(&self) -> Element<Message> {
        let search_input = text_input(
            &i18n::t("fp.search.placeholder"),
            &self.flatpak_search_query,
        )
        .on_input(Message::SearchQueryChanged)
        .width(Length::FillPortion(4));

        let search_btn = button(text(i18n::t("fp.search")))
            .on_press(Message::SearchFlatpaks);

        let list_installed_btn = button(text(i18n::t("fp.refresh_installed")))
            .on_press(Message::ListInstalledFlatpaks);

        let mut results_list = column![];
        for app in &self.flatpak_search_results {
            let install_btn = button(text("Install"))
                .on_press(Message::InstallFlatpak(app.appid.clone()));
            
            let app_row = row![
                text(&app.name).width(Length::Fill),
                install_btn,
            ]
            .spacing(10);
            results_list = results_list.push(app_row);
        }

        let status = text(&self.flatpak_status);

        column![
            row![search_input, search_btn, list_installed_btn].spacing(10),
            status,
            scrollable(results_list).height(Length::Fill),
        ]
        .spacing(10)
        .into()
    }

    fn view_settings_tab(&self) -> Element<Message> {
        column![
            row![
                text(i18n::t("settings.language")).width(Length::FillPortion(1)),
                text(&self.config.language).width(Length::FillPortion(1)),
            ]
            .spacing(10)
            .align_items(Alignment::Center),
            row![
                text(i18n::t("settings.theme")).width(Length::FillPortion(1)),
                text(&self.config.theme).width(Length::FillPortion(1)),
            ]
            .spacing(10)
            .align_items(Alignment::Center),
        ]
        .spacing(20)
        .into()
    }
}
