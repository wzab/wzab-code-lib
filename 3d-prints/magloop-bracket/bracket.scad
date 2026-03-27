$fn=300;
//Wydruk w pionie i bez podpor
dlug=20;
szer=15;
wys=40;

szer_moc=6;
gleb_moc=2;

srednica_sruba=4;
srednica_leb=7;
gleb_leb=2;

module otwor_sruba() {
  rotate([0,90,0]){
  union(){
      translate([0,0,-1])cylinder(2*dlug,d1=srednica_sruba,d2=srednica_sruba,center=true);
      translate([0,0,+6])cylinder(dlug,d1=srednica_leb,d2=srednica_leb,center=true);      
  }  
  }
}
module mocowanie() {translate([-(dlug-szer)/2+gleb_moc,0,0]){
        difference(){
            cylinder(h=szer_moc,d1=2*dlug,d2=2*dlug,center=true);
            cylinder(h=szer_moc+1,d1=szer,d2=szer,center=true);
            translate([dlug,0,0]){cube([2*dlug,2*dlug,2*dlug],center=true);
            }
        }
    };
}

difference() {
    cube([dlug,szer,wys],center=true);
    translate([dlug/2,0,0]){
      rotate([0,0,45]){
         cube([szer,szer,wys+10], center=true);       
      }
    }
    translate([0,0,0]){
        mocowanie();
    }
    translate([0,0,(wys+szer_moc)/4]){
        otwor_sruba();
    }
    translate([0,0,-(wys+szer_moc)/4]){
        otwor_sruba();
    }
}