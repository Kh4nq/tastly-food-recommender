import type {Text} from "@/lib/i18n";

const avt_path = "/team_member/"

type Member = {
    name : string;
    role : Text;
    avatar : string;
    email : string;
    phone : string;
    linkedin : string;
    github : string;
}

export const members: Member[] = [
  {
    name: "Huỳnh Bảo Khang",
    role: { vi: "Trưởng nhóm · Fullstack", en: "Team lead · Fullstack" },
    avatar: `${avt_path}bkhang.jpg`,
    email: "khanghb.ti.2124@gmail.com",
    phone: "0784024880",
    linkedin: "https://www.linkedin.com/in/hu%E1%BB%B3nh-b%E1%BA%A3o-khang-87457138a/",
    github: "https://github.com/khanghb2006/",
  },
  {
    name: "Nguyễn Phước Khang",
    role: { vi: "AI Engineer", en: "AI Engineer" },
    avatar: `${avt_path}pkhang.jpg`,
    email: "nguyentuvt3112@gmail.com",
    phone: "0783462622",
    linkedin: "https://www.linkedin.com/in/khang-nguy%E1%BB%85n-680753391/",
    github: "https://github.com/Kh4nq",
  },
  {
    name: "Phạm Minh Đạt",
    role: { vi: "Web Developer - Data Engineer", en: "Web Developer - Data Engineer" },
    avatar: `${avt_path}mdat.png`,
    email: "24120174@student.hcmus.edu.vn",
    phone: "0858480666",
    linkedin: "https://www.linkedin.com/in/m1hdat/",
    github: "https://github.com/m1hdat",
  },
  {
    name: "Trần Huy",
    role: { vi: "AI Engineer", en: "AI Engineer" },
    avatar: `${avt_path}lehuy.jpg`,
    email: "trandanglehuy2006@gmail.com",
    phone: "0918542006",
    linkedin: "https://www.linkedin.com/in/celebken/",
    github: "https://github.com/celebken",
  },
];
